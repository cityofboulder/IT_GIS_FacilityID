import os
import shelve
from datetime import date, datetime

import facilityid.config as config
from arcpy import AddJoin_management, ClearWorkspaceCache_management
from arcpy.da import Editor, UpdateCursor
from arcpy.mp import ArcGISProject, LayerFile

from .identifier import Identifier
from .management import write_to_csv

# Initialize the logger for this file
log = config.logging.getLogger(__name__)


def _merge(x):
    """Concatenate an ID back together."""

    p = x['FACILITYID']['prefix']
    i = x['FACILITYID']['str_id']
    return p + i


class Edit(Identifier):
    """A class meant to be used once a table has been slated for edits.

    Parameters
    ----------
    rows : list
        A list of dictionaries, where each dict represents a row of the
        table
    duplicates : list
        A list of GLOBALIDs that have duplicated FACILITYIDs
    used : list
        A reverse sorted list of used IDs in the table
    unused : list
        A reverse sorted list of unused IDs between the min and max of
        used IDs
    """

    edited_users = list()  # Data owners that had edits performed
    edited_features = list()  # Counts of edits required for each layer
    version_failures = list()  # Layers that can't have versioned edits done

    def __init__(self, tuple_path):
        super().__init__(tuple_path)
        self.rows = self.rows()
        self.duplicates = self.duplicates()
        self.used = self._used()
        self.unused = self._unused()

    def __hash__(self):
        return hash(self.__key())

    def __key(self):
        guid_facid_pairs = [(x['GLOBALID'], _merge(x)) for x in self.rows]
        key = tuple(sorted(guid_facid_pairs, key=lambda y: y[0]))
        return key

    def add_edit_metadata(self):
        self.edited_features.append(self.count)
        if self.owner not in self.edited_users:
            self.edited_users.append(self.owner)

    def _used(self):
        """Extracts a list of used ids in rows, sorted in reverse order.

        Returns
        -------
        list
            Used IDs between min and max utilized IDs
        """
        all_used = sorted(
            [x["FACILITYID"]["int_id"]
             for x in self.rows if x["FACILITYID"]["int_id"] is not None],
            reverse=True)
        return all_used

    def _unused(self) -> list:
        """Extracts a list of unused ids that lie between the minimum
        and maximum ids in order to backfill gaps in ID sequences.

        Returns
        -------
        list
            Unused IDs between the minimum and maximum utilized IDs
        """

        min_id = self.used[-1]

        # initiate a try block in case the max id is too large to compute a set
        # and overflows computer memory
        for m in self.used:
            try:
                set_of_all = set(range(min_id, m))
                set_of_used = set(self.used)
                unused = sorted(list(set_of_all - set_of_used), reverse=True)
                break
            except (OverflowError, MemoryError):
                continue

        return unused

    def _new_id(self) -> int:
        """Finds the next best ID to apply to a row with missing or
        duplicated IDs.

        This function modifies both inputs by either popping the last
        item off the end of the unused list or incrementing the used
        list by 1

        Parameters
        ----------
        used : list
            A list of used IDs in the table, sorted in reverse order.
        unused : list
            A list of unused IDs between the minimum and maximum IDs in
            the feature class, sorted in reverse order.

        Returns
        -------
        int
            An integer number representing the next logical ID to assign
        """

        if self.unused:
            new_id = self.unused.pop()
        else:
            max_id = self.used[0] + 1
            new_id = max_id
            self.used.insert(0, max_id)

        return new_id

    def _sorter(self, x):
        """A function meant to be used in the builtin sort function for
        lists.

        Dynamically sorts the lists of duplicates based on the shape
        type of the feature class in question.

        Parameters
        ----------
        x : dict
            Represents a single row from the list of rows

        Returns
        -------
        tuple
            A tuple that dictates how to multi-sort
        """

        # Define date to replace Null values in the sort
        # Null values first, followed byt oldest to newest
        _null_date = datetime(1400, 1, 1)
        geo = self.shapeType if self.datasetType == 'FeatureClass' else ''

        def geom_sorter(g):
            """Determines the proper field to sort on based
            on the spatial data type."""

            if g == 'Polygon':
                return - x['SHAPE@'].area
            elif g == 'Polyline':
                return - x['SHAPE@'].length
            else:
                return (x['CREATED_DATE'] or _null_date)

        sort_1 = _merge(x)
        sort_2 = geom_sorter(geo)
        sort_3 = (x['LAST_EDITED_DATE'] or _null_date)

        return (sort_1, sort_2, sort_3)

    def _format_edit_row(self, row, old_facid):
        result = {"DATE": str(date.today()),
                  "TIME": datetime.now().strftime("%H:%M:%S"),
                  "OWNER": self.owner,
                  "FEATURE": self.name,
                  "GLOBALID": row["GLOBALID"],
                  "OLDFACILITYID": old_facid,
                  "NEWFACILITYID": _merge(row)}
        return result

    def _edit(self):
        """Iterates through a list of rows, editing incorrect or
        duplicated entries along the way.

        This method edits duplicated FACILITYIDs first, followed by
        incorrect or missing FACILITYIDs. It also modifies the used and
        unused attributes of the class. Ultimately the edited attribute
        will be populated if edits were made to the table.

        The method knows to edit incorrect IDs based on the following
        criteria:

        Prefix is not capitalized
        Prefix of the row does not exist
        Prefix does not equal the layer's designated prefix
        The ID does not exist
        The ID has leading zeros
        The ID has already been used

        Returns
        -------
        list
            A list of dicts, where each dict represents a row that has
            had its FACILITYID changed.
        """

        # Initialize a dict that will count the kinds of edits required
        self.count = {"0 - Feature": self.feature_name,
                      "1 - # Empty IDs": 0,
                      "2 - # Incorrect IDs": 0,
                      "3 - # Duplicated IDs": 0,
                      "4 - Total Edits": 0}

        edited = list()
        if self.duplicates:
            log.debug("Identifying duplicated Facility IDs...")
            # Identify rows that contain duplicate FACILITYIDs with the correct
            # prefix
            dup_rows = [row for row in self.rows if row['GLOBALID']
                        in self.duplicates and row['FACILITYID']['prefix']
                        == self.prefix]
            # Perform the sort
            dup_rows.sort(key=self._sorter)
            # Iterate through each unique ID in the duplicated rows
            distinct = set([_merge(r) for r in dup_rows])
            for i in distinct:
                chunk = [x for x in dup_rows if _merge(x) == i]
                # The last ID of the list (e.g. 'chunk[-1]'), does not need to
                # be edited, since all of its dupes have been replaced
                for c in chunk[:-1]:
                    # Count how many duplicates were QC'd
                    self.count["3 - # Duplicated IDs"] += 1

                    edit_row = self.rows[self.rows.index(c)]
                    new_id = self._new_id()
                    edit_row["FACILITYID"]["int_id"] = new_id
                    edit_row["FACILITYID"]["str_id"] = str(new_id)
                    r = self._format_edit_row(edit_row, i)
                    edited.append(r)

        log.debug("Inspecting all other rows in the table...")
        for edit_row in self.rows:
            if edit_row in edited:
                continue
            # Flag whether edits need to be made to the row
            # Assume no edits to start
            edits = False
            old_facid = _merge(edit_row)
            pfix = edit_row["FACILITYID"]["prefix"]
            str_id = edit_row["FACILITYID"]["str_id"]
            # int_id = edit_row["FACILITYID"]["int_id"]
            empty = not pfix and not str_id

            # Count whether the ID is empty
            if empty:
                self.count["1 - # Empty IDs"] += 1

            # PREFIX EDITS
            if not pfix or not pfix.isupper() or pfix != self.prefix:
                edit_row["FACILITYID"]["prefix"] = self.prefix
                edits = True

            # ID EDITS
            # if not str_id or len(str_id) != len(str(int_id)):
            if not str_id:
                new_id = self._new_id()
                edit_row["FACILITYID"]["int_id"] = new_id
                edit_row["FACILITYID"]["str_id"] = str(new_id)
                edits = True

            if edits:
                # Count total # of edits
                self.count["4 - Total Edits"] += 1

                # Count whether the ID is incorrect...
                # (if edits are required but the ID was not empy)
                if not empty:
                    self.count["2 - # Incorrect IDs"] += 1

                r = self._format_edit_row(edit_row, old_facid)
                edited.append(r)

        return edited

    def version_essentials(self) -> bool:
        """Tests whether the feature is eligible for versioned edits.

        In order to be edited, the feature must have been authorized

        Returns
        -------
        bool
            Whether the object passes the test
        """

        result = False  # Assume the layer will be skipped
        essentials = {
            "1 - Register as Versioned": self.isVersioned,
            "2 - Grant GISSCR Privileges": self.can_gisscr_edit(config.edit)}

        if self.owner in config.versioned_edits:
            if all(essentials.values()):
                result = True
            else:
                # Catalog what went wrong and log to the failures variable
                wrong = {"0 - Feature": self.feature_name}
                for k, v in essentials.items():
                    wrong = {**wrong, k: "X" if not v else ""}
                self.version_failures.append(wrong)
        else:
            log.debug(f"{self.owner} has not authorized versioned edits...")

        return result

    def add_to_aprx(self, edit_rows, csv_file: str):
        """Adds the input layer to a .aprx Map based on the owner of the
        data. For example, the UTIL.wFitting feature would be added to the
        "UTIL" map of the designated .aprx file. The file path to the Pro
        project is set in the config file.

        Parameters:
        -----------
        edits_rows : list
            A list of rows represented as dictionaries
        csv_file : str
            File path to the csv file containing edited rows
        """

        log.debug("Adding the layer to its edit aprx...")
        aprx = ArcGISProject(config.aprx)
        user_map = aprx.listMaps(f"{self.owner}")[0]
        user_map.addDataFromPath(self.aprx_connection)
        layer = user_map.listLayers(self.feature_name)[0]
        aprx.save()

        # Create group layer if it does not exist
        lyr_realpath = os.path.realpath(config.lyr)
        lyr_basename = os.path.basename(config.lyr)
        if self.version_name not in [x.name for x in
                                     user_map.listLayers()]:
            # Add to the map
            user_map.addLayer(LayerFile(lyr_realpath))
            aprx.save()
            # Rename the group layer to match the version name
            layer_name = lyr_basename.strip('.lyrx')
            for lyr in user_map.listLayers():
                if lyr.name == layer_name:
                    lyr.name = self.version_name
                    break

        # Move into the group layer
        try:
            group_layer = user_map.listLayers(self.version_name)[0]
            user_map.addLayerToGroup(group_layer, layer)
            user_map.removeLayer(layer)
            aprx.save()
            layer = user_map.listLayers(self.feature_name)[0]
        except IndexError:
            log.exception(f"No group layer exists in the {self.owner} map...")

        log.debug("Joining csv file to the layer in Pro...")
        AddJoin_management(layer, "GLOBALID", csv_file, "GLOBALID")
        aprx.save()

    def edit_version(self, connection_file: str):

        records = self._edit()
        if records:
            log.debug("Writing edited rows to a csv...")
            csv_file = f'.\\facilityid\\log\\{self.feature_name}_Edits.csv'
            write_to_csv(csv_file, records)

            self.add_edit_metadata()

            guid_facid = {x['GLOBALID']: x["NEWFACILITYID"] for x in records}
            if connection_file:
                edit_conn = os.path.join(connection_file, *self.tuple_path[1:])
                try:
                    # Start an arc edit session
                    log.debug("Entering an arc edit session...")
                    editor = Editor(connection_file)
                    editor.startEditing(False, True)
                    editor.startOperation()

                    log.debug("Filtering the table to editted records only...")
                    # Query only the entries that need editing
                    guids = ", ".join(f"'{x}'" for x in guid_facid.keys())
                    query = f"GLOBALID IN ({guids})"

                    # Open an update cursor and perform edits
                    log.debug("Opening an update cursor to perform edits...")
                    fields = ["GLOBALID", "FACILITYID"]
                    with UpdateCursor(edit_conn, fields, query) as cursor:
                        for row in cursor:
                            row[1] = guid_facid[row[0]]
                            cursor.updateRow(row)

                    # Stop the edit operation
                    log.debug("Closing the edit session...")
                    editor.stopOperation()
                    editor.stopEditing(True)
                    del editor
                    ClearWorkspaceCache_management()

                    log.info(("Successfully performed versioned edits on "
                              f"{self.feature_name}..."))
                    # Reset the aprx connection to the versioned connection
                    self.aprx_connection = edit_conn
                    self.version_name = os.path.basename(
                        connection_file).strip(".sde")
                    self.add_to_aprx(records, csv_file)
                except RuntimeError:
                    log.exception(("Could not perform versioned edits "
                                   f"on {self.feature_name}..."))
            log.debug("Logging edits to csv file containing all edits ever...")
            all_edits = r'.\\facilityid\\log\\AllEditsEver.csv'
            write_to_csv(all_edits, records)
        else:
            log.info("No edits were necessary...")

    def store_current(self):
        with shelve.open('.\\facilityid\\log\\previous_run', 'c') as db:
            db[self.feature_name] = self.__key()

    def equals_previous(self):
        try:
            with shelve.open('.\\facilityid\\log\\previous_run', 'c') as db:
                previous = db[self.feature_name]
            if hash(self) == hash(previous):
                return True
            else:
                return False
        except KeyError:
            log.debug(f"{self.feature_name} has never been scanned...")
            pass  # Gets stored later in the script, no need to store at error
