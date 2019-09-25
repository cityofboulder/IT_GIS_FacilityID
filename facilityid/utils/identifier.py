from arcpy import ArcSDESQLExecute, Describe, ExecuteError, GetCount_management, ListFields
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
        """Determines if the feature class has the FACILITYID field."""
        return True if "FACILITYID" in self.fields else False

    def has_globalid(self):
        """Determines if the feature class has the GLOBALID field."""
        return True if "GLOBALID" in self.fields else False

    def find_prefix(self):
        """Determines the prefix of the feature class based on the most prevalent occurrence."""
        # TODO: fill in code
        return True

    # TODO: Add a function that converts each row of the fc to a dict {"GLOBALID": , "FACILITYID": , "CREATED": , "EDITED": }
