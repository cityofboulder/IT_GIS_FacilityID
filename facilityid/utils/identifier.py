from arcpy import ArcSDESQLExecute, Describe, ExecuteError, GetCount_management, ListFields
from arcpy.da import SearchCursor
from os import path


class Identifier(ArcSDESQLExecute):
    """A class intended to deal with the specifics of controlling for the quality of Facility IDs. This builds upon the
    Describe object in arcpy."""
    def __init__(self, iterator_path):
        super().__init__()  # Initialize the super-class just to be explicit
        self.full_path = path.join(*iterator_path)
        self._desc = Describe(self.full_path)
        self.fields = [f.name for f in ListFields(self.full_path) if not f.required]
        self.prefix = self.find_prefix()

    def __getattr__(self, item):
        """Pass any other attribute or method calls through to the underlying Describe object"""
        return getattr(self._desc, item)

    def has_records(self):
        """Determines if there are any records in the feature class to analyze."""
        try:
            count = int(GetCount_management(self.full_path).getOutput(0))
            return True if count >= 1 else False
        except ExecuteError:
            # TODO: Add info logging describing an error in retrieving a feature count
            return None

    def has_facilityid(self):
        """Determines if the feature class has the FACILITYID field.

        :return: Boolean, True if FACILITYID is a field in the SDE item
        """
        return True if "FACILITYID" in self.fields else False

    def has_globalid(self):
        """Determines if the feature class has the GLOBALID field.

        :return: Boolean, True if the SDE item has a GLOBALID field
        """
        return True if "GLOBALID" in self.fields else False

    def has_table(self):
        """Identifies whether an item in the SDE is a feature class or table

        :return: Boolean, true if the item is a feature class or table
        """
        return True if self._desc.dataType in ['FeatureClass', 'Table'] else False

    def find_prefix(self):
        """Determines the prefix of the feature class based on the most prevalent occurrence."""
        # TODO: fill in code
        return True

    def get_rows(self):
        """Opens an arcpy SearchCursor and records fields relevant to the QC of FACILITYID

        :return: List, rows represented as dictionaries within a list
        """
        fields = ['GLOBALID', 'FACILITYID', 'CREATED_USER', 'CREATED_DATE', 'LAST_EDITED_USER', 'LAST_EDITED_DATE']
        if self._desc.dataType == 'FeatureClass':
            fields.append('SHAPE@')
        row_list = []
        with SearchCursor(self.full_path, fields) as search:
            for row in search:
                row_list.append({fields[i]: row[i] for i in range(len(row))})
        return row_list
