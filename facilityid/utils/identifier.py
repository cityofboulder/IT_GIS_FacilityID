import os
import re

from arcpy import ArcSDESQLExecute, Describe, ExecuteError, ListFields
from arcpy.da import SearchCursor


class Identifier:
    """A class intended to deal with the specifics of controlling for
    the quality of Facility IDs. This class inherits the functionality
    of the arcpy.Describe function.
    """

    def __init__(self, tuple_path):
        self.tuple_path = tuple_path
        self.full_path = os.path.join(*self.tuple_path)
        self.connection = self.tuple_path[0]
        self.dataset = self._dataset()
        self.feature_name = self.tuple_path[-1]
        self.owner = self._owner()
        self.name = self._name()
        self.database_name = self._database_name()
        self.shape = self._shape()

        self.has_table = self.datasetType in ['FeatureClass', 'Table']
        self.fields = [f.name for f in ListFields(self.full_path)]
        self.has_facilityid = "FACILITYID" in self.fields
        self.has_globalid = "GLOBALID" in self.fields
        self.prefix = self._prefix()

        self._desc = Describe(self.full_path)

    def __getattr__(self, item):
        """Pass any other attribute or method calls through to the
        underlying Describe object"""
        return getattr(self._desc, item)

    def _database(self):
        """Return the database client name"""
        parts = self.feature_name.split('.')

        # SQL Server follows the pattern db.owner.name
        if len(parts) == 3:
            db = 'MSSQL'
        # Oracle follows the pattern owner.name
        else:
            db = 'ORACLE'

        return db

    def _dataset(self):
        """Return the name of the dataset, if it exists"""
        return self.tuple_path[1] if len(self.tuple_path) == 3 else None

    def _owner(self):
        """Get the name of the feature's owner"""
        parts = self.feature_name.split('.')

        if self._database() == 'MSSQL':
            owner = parts[1]
        if self._database() == 'ORACLE':
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
        if self._database() == 'ORACLE':
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
                return result[0]
            except (ExecuteError, TypeError, AttributeError):
                return None
        else:
            return None

    def record_count(self) -> bool:
        """Determines if there are any records in the feature class to
        analyze."""
        execute_object = ArcSDESQLExecute(self.connection)
        try:
            query = f"""SELECT COUNT(*) FROM {self.database_name}"""
            result = execute_object.execute(query)
            return int(result)
        except ExecuteError:
            # TODO: Add info logging
            return None

    def duplicates(self):
        # Initialize an executor object for SDE
        execute_object = ArcSDESQLExecute(self.connection)
        query = f"""SELECT a.FACILITYID,
                    a.GLOBALID
                    FROM {self.database_name} a
                    JOIN (SELECT FACILITYID,
                        GLOBALID,
                        COUNT(*)
                        FROM {self.database_name}
                        GROUP BY FACILITYID, GLOBALID
                        HAVING COUNT(*) > 1) b
                    ON a.GLOBALID = b.GLOBALID"""
        try:
            result = execute_object.execute(query)
            globalids = [r[1] for r in result if r[0]]
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
        for row in result:
            if row[0] in ("UPDATE", "INSERT", "DELETE"):
                editable = True
                break
        return editable
