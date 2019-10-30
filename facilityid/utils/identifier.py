import os
import re

from arcpy import ArcSDESQLExecute, Describe, ExecuteError, ListFields
from arcpy.da import SearchCursor


class Identifier:
    """A class intended to deal with the specifics of controlling for the quality of Facility IDs. 
    This class inherits the functionality of the arcpy.Describe function.
    """

    def __init__(self, tuple_path):
        self.tuple_path = tuple_path
        self.full_path = os.path.join(*self.tuple_path)
        self.connection = self.tuple_path[0]
        self.dataset = self.tuple_path[1] if len(
            self.tuple_path) == 3 else None
        self.owner, self.name = tuple_path[-1].split(".")
        self.database_name = ".".join([self.owner, self.name[:26]]).upper() + \
            "_EVW" if self.isVersioned else ".".join(
                [self.owner, self.name[:30]]).upper()

        self.fields = [f.name for f in ListFields(self.full_path)]
        self.has_facilityid = True if "FACILITYID" in self.fields else False
        self.has_globalid = True if "GLOBALID" in self.fields else False
        self.has_table = True if self.datasetType in [
            'FeatureClass', 'Table'] else False
        self.has_records = True if self.record_count(
        ) is not None or self.record_count() >= 1 else False
        self.prefix = self.find_prefix()

        self._desc = Describe(self.full_path)

    def __getattr__(self, item):
        """Pass any other attribute or method calls through to the underlying Describe object"""
        return getattr(self._desc, item)

    def record_count(self) -> bool:
        """Determines if there are any records in the feature class to analyze."""
        execute_object = ArcSDESQLExecute(self.connection)
        try:
            query = f"""SELECT COUNT(*) FROM {self.database_name}"""
            result = execute_object.execute(query)
            return int(result)
        except ExecuteError:
            # TODO: Add info logging describing an error in retrieving a feature count
            return None

    def find_prefix(self):
        """Determines the prefix of the feature class based on the most prevalent occurrence."""
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

    def get_duplicates(self):
        # Initialize an executor object for SDE
        execute_object = ArcSDESQLExecute(self.connection)
        query = f"""SELECT a.GLOBALID,
                    a.FACILITYID
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
            return result
        except (ExecuteError, TypeError, AttributeError):
            return None

    def get_rows(self):
        """Extracts a feature's table for analysis
        
        Extracts FACILITYID, GLOBALID, edit metadata, and SHAPE fields 
        of a feature class or table. Edit metadata fields are
        dynamically assigned based on attributes of a fc's describe obj.
        FACILITYIDs are further broken into {"prefix": x, "str_id": y, 
        "int_id": z}.
        
        Returns
        -------
        list
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
                row_list.append({fields[i]: row[i] for i in range(len(fields))})
        
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

        return row_list

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

def get_ids(in_list: list) -> (int, list):
    """Extracts the maximum id and a list of all unused ids up to the
    maximum.
    
    Parameters
    ----------
    in_list : list
        The list of dict-like rows created by the get_rows method. 
    
    Returns
    -------
    tuple
        Maximum ID used by the layer, and a reverse sorted list of
        unused ids between the minimum and maximum id.
    """
    used = sorted([x["FACILITYID"]["int_id"]
                  for x in in_list if x["FACILITYID"]["int_id"] is not None],
                  reverse=True)
    min_id = used[-1]
    max_id = used[0]

    # initiate a try block in case the max id is too large to compute a 
    # set and overflows computer memory
    for m in used:
        try:
            set_of_all = set(range(min_id, m))
            set_of_used = set(used)
            unused = sorted(list(set_of_all - set_of_used), reverse=True)
            break
        except (OverflowError, MemoryError):
            continue

    return (max_id, unused)