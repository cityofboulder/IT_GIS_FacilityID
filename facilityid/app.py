# TODO: place globals into yml config file
# TODO: transfer items from personal modules into a project utilities module
# TODO: figure out how to download the boulder_gis package into conda env
import json
import getpass
from datetime import datetime

from .utils.management import delete_facilityid_versions, clear_layers_from_map, find_in_sde
from .utils.identifier import Identifier

"""Read in config.json and assign values to variables"""
with open('config.json') as config_file:
    configs = json.load(config_file)
# Boolean for scripted post control
post_control = configs["post_edits"]
# SDE database connection file locations
read_connection = configs["sde"]["read"]
edit_connection = configs["sde"]["edit"]
# Tags designating how to check IDs
scan_mode = [k for k, v in configs["mode"].items() if v]
# Designate which users have authorized scripted edits
authorize_scripted_edits = [k for k, v in configs["users"].items() if v]
# Designate which users to check IDs for
users_to_check = configs["users"].keys(
) if "scan_by_user" in scan_mode else list()
# Designate which data sets to check IDs for
dsets_to_check = configs["dsets"] if "scan_by_dset" in scan_mode else list()
# Designate which features to check IDs for
feats_to_check = configs["feats"] if "scan_by_feat" in scan_mode else list()
# Combines all filter elements into one list
filters = users_to_check + dsets_to_check + feats_to_check

"""Define variables that are constant throughout the script"""
# User who initiated the script
username = getpass.getuser()
# Day and time script was run
start_date_string = datetime.now().strftime("%Y%m%d")
start_time_string = datetime.now().strftime('%H%M')
# Define what a row in the sde checklist looks like
checklist_row = configs["checklist"]
# Define what a row in the edit summary looks like
edit_counts_row = configs["count"]


def main():
    # Step 1: Delete all existing Facility ID versions
    delete_facilityid_versions(edit_connection)

    # Step 2: Clear layers from all edit maps in Pro
    clear_layers_from_map()

    # Step 3: Obtain tuples of system paths for every fc
    features = find_in_sde(read_connection, filters)

    # Step 4: Iterate through each feature
    for feature in features:
        # Step 4a: Initialize an identifier object
        facilityid = Identifier(feature)

        # Step 4b: Make preliminary checks before analyzing the feature
        essentials = [facilityid.has_table,
                      facilityid.has_facilityid,
                      facilityid.has_globalid,
                      facilityid.editorTrackingEnabled,
                      facilityid.prefix]
        non_essentials = [facilityid.isVersioned,
                          facilityid.can_gisscr_edit(edit_connection)]
        if not all(essentials):
            # TODO: log that the layer will not be analyzed
            continue

        # Step 4c: Extract rows
        table = facilityid.get_rows()

        # Step 4d: Identify the GLOBALIDs of duplicated FACIDs
        duplicates = facilityid.get_duplicates()

        # Step 4e: Make edits to each row
