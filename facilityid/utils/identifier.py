import os
import re

import facilityid.config as config
from arcpy import ArcSDESQLExecute, Describe, ExecuteError, ListFields
from arcpy.da import SearchCursor

# Initialize the logger for this file
log = config.logging.getLogger(__name__)


class Identifier:
    """A class intended to deal with the specifics of controlling for
    the quality of Facility IDs. This class inherits the functionality
    of the arcpy.Describe function.
    """

    inspected_users = list()  # list all users that were inspected
    failures = list()  # list of all layers that failed evaluation

    def __init__(self, tuple_path):
        self.tuple_path = tuple_path
        self.full_path = os.path.join(*self.tuple_path)
        self._desc = Describe(self.full_path)

        self.connection = self.tuple_path[0]
        self.database = config.db  # Database platform from config file
        self.dataset = self._dataset()
        self.feature_name = self.tuple_path[-1]
        self.owner = self._owner()
        self.name = self._name()
        self.database_name = self._database_name()

        self.has_table = self.datasetType in ['FeatureClass', 'Table']
        self.fields = self._fields()
        self.has_facilityid = "FACILITYID" in self.fields
        self.has_globalid = "GLOBALID" in self.fields
        self.prefix = self._prefix()
        self.shape = self._shape()

    def __getattr__(self, item):
        """Pass any other attribute or method calls through to the
        underlying Describe object"""
        return getattr(self._desc, item)

    def _dataset(self):
        """Return the name of the dataset, if it exists"""
        return self.tuple_path[1] if len(self.tuple_path) == 3 else None

    def _owner(self):
        """Get the name of the feature's owner"""
        parts = self.feature_name.split('.')

        if len(parts) == 3:  # SQLSERVER names are DATABASE.OWNER.FEATURE
            owner = parts[1]
        else:  # ORACLE names are OWNER.FEATURE
            owner = parts[0]

        return owner

    def _name(self):
        """Get the name of the feature"""
        return self.feature_name.split('.')[-1]

    def _database_name(self):
        """Get the name of the layer inside the spatial database.

        Output will be different depending on whether SQL Spatial or
        Oracle databases are being used. Oracle imposed a 30 char limit
        on table names, while SQL Server has a 120 char limit.

        Returns:
        --------
        str
            The name of the table inside the database.
        """

        name = ".".join([self.owner, self.name[:128]]).upper()
        if self.database == 'ORACLE':
            if self.isVersioned:
                name = ".".join([self.owner, self.name[:26]]).upper() + "_EVW"
            else:
                name = ".".join([self.owner, self.name[:30]]).upper()

        return name

    def _shape(self):
        return self.shapeType if self.datasetType == 'FeatureClass' else ''

    def _prefix(self):
        """Determines the prefix of the feature class based on the most
        prevalent occurrence."""
        if self.has_facilityid:
            # Initialize an executor object for SDE
            execute_object = ArcSDESQLExecute(self.connection)
            query = f"""SELECT REGEXP_SUBSTR(FACILITYID, '^[a-zA-Z]+') as PREFIXES,
                    COUNT(*) as PFIXCOUNT
                    FROM {self.database_name}
                    GROUP BY REGEXP_SUBSTR(FACILITYID, '^[a-zA-Z]+')
                    ORDER BY PFIXCOUNT DESC
                    FETCH FIRST ROW ONLY"""
            try:
                result = execute_object.execute(query)
                return result[0][0]
            except (ExecuteError, TypeError, AttributeError):
                return None
        else:
            return None

    def _fields(self):
        """Determines the field names in the table
        """
        try:
            result = [f.name for f in ListFields(self.full_path)]
        # If a feature is a network dataset or topology, no fields exist
        # and a RuntimeError is raised
        except RuntimeError:
            result = list()
        return result

    def record_count(self) -> int:
        """Determines if there are any records in the feature class to
        analyze."""
        execute_object = ArcSDESQLExecute(self.connection)
        try:
            query = f"""SELECT COUNT(*) FROM {self.database_name}"""
            result = execute_object.execute(query)
            return int(result)
        except ExecuteError:
            # TODO: Add info logging
            return 0

    def essentials(self) -> bool:
        """Tests whether the feature is eligible for a Facility ID scan.

        In order to be considered for a scan, the layer must have a
        GLOBALID filed, have editor tracking turned on, and have at
        least one record that contains a Facility ID.

        Returns
        -------
        bool
            Whether the object passes the test
        """

        result = False  # Assume the layer will be skipped
        if self.has_table:
            if self.has_facilityid:
                essentials = {"1 - Enable GLOBALIDs": self.has_globalid,
                              "2 - Enable Editor Tracking":
                              self.editorTrackingEnabled,
                              "3 - Give one record an ID":
                              self.prefix and self.record_count() > 0}
                if all(essentials.values()):
                    if self.owner not in self.inspected_users:
                        self.inspected_users.append(self.owner)
                    result = True
                else:
                    # Catalog what went wrong and log to the failures variable
                    wrong = {"0 - Feature": self.feature_name}
                    for k, v in essentials.items():
                        wrong = {**wrong, k: "X" if not v else ""}
                    self.failures.append(wrong)
                    log.warning(f"{self.feature_name} is being skipped "
                                "because it is missing an essential "
                                "requirement for the script to run...")
            else:
                log.warning((f"{self.feature_name}  does not have a "
                             "FACILITYID field..."))
        else:
            log.warning((f"{self.feature_name} does not qualify for "
                         "analysis because it is not a feature class "
                         "or table..."))

        return result

    def duplicates(self):
        # Initialize an executor object for SDE
        execute_object = ArcSDESQLExecute(self.connection)
        query = f"""SELECT a.GLOBALID,
                           a.FACILITYID
                    FROM {self.database_name} a
                    INNER JOIN (
                        SELECT FACILITYID
                        FROM {self.database_name}
                        GROUP BY FACILITYID
                        HAVING COUNT(*) > 1
                    ) dups
                    ON dups.FACILITYID = a.FACILITYID"""

        try:
            result = execute_object.execute(query)
            globalids = [r[0] for r in result if r[1]]
            return globalids
        except (ExecuteError, TypeError, AttributeError):
            # TODO: Add logging
            return list()

    def rows(self):
        """Extracts a feature's table for analysis

        Extracts FACILITYID, GLOBALID, edit metadata, and SHAPE fields
        of a feature class or table. Edit metadata fields are
        dynamically assigned based on attributes of a fc's describe obj.
        FACILITYIDs are further broken into {"prefix": x, "str_id": y,
        "int_id": z}.

        Returns
        -------
        tuple
            rows represented as dicitionaries
        """

        edit_fields = [self.creatorFieldName,
                       self.createdAtFieldName,
                       self.editorFieldName,
                       self.editedAtFieldName]
        fields = ['GLOBALID', 'FACILITYID'] + edit_fields
        if self.datasetType == 'FeatureClass':
            fields.append('SHAPE@')

        row_list = []
        with SearchCursor(self.full_path, fields) as search:
            for row in search:
                row_list.append({fields[i]: row[i]
                                 for i in range(len(fields))})

        # Transform the output of the FACILITYID field by breaking apart
        # the value into prefix, id as string, and id as integer
        for row in row_list:
            if row["FACILITYID"]:
                f_id = str(row["FACILITYID"])
                # Use regex to find the prefix of the row's FACILITYID
                try:
                    pfix = re.findall(r"^\D+", f_id)[0]
                # re.findall returns [] if the pattern doesn't exist
                except IndexError:
                    pfix = ""

                # Define the ID as everything following the prefix
                id_str = f_id[len(pfix):]

                # Convert the string ID to integer
                try:
                    id_int = int(id_str)
                # if id_str has non-numeric chars, assume no ID
                except ValueError:
                    id_str = ""
                    id_int = None

                row["FACILITYID"] = {"prefix": pfix,
                                     "str_id": id_str,
                                     "int_id": id_int}
            else:
                row["FACILITYID"] = {"prefix": "",
                                     "str_id": "",
                                     "int_id": None}

        return tuple(row_list)

    def can_gisscr_edit(self, connection) -> bool:
        """Reveals if the feature class is editable through the GISSCR connection.

        :param connection: File path to an SDE connection with the GISSCR user
        :return: Boolean
        """
        query = f"""SELECT PRIVILEGE
                   FROM ALL_TAB_PRIVS
                   WHERE TABLE_NAME = '{self.name.upper()}'
                   AND TABLE_SCHEMA = '{self.owner.upper()}'"""
        execute_object = ArcSDESQLExecute(connection)
        result = execute_object.execute(query)
        editable = False  # Assume GISSCR user cannot edit by default
        try:
            for row in result:
                if row[0] in ("UPDATE", "INSERT", "DELETE"):
                    editable = True
                    break
        except TypeError:
            pass  # result = True when the table cannot be accessed by GISSCR
        return editable
