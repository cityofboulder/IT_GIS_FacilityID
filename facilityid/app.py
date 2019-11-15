# TODO: place globals into yml config file
# TODO: transfer items from personal modules into a project utilities module
# TODO: figure out how to download the boulder_gis package into conda env
import getpass
import datetime

import config
from utils.management import (delete_facilityid_versions,
                              clear_layers_from_map, find_in_sde)
from utils.identifier import Identifier
from utils.edit import Edit

"""Define variables that are constant throughout the script"""
# User who initiated the script
username = getpass.getuser()

# Day and time script was run
start_date_string = datetime.datetime.now().strftime("%Y%m%d")
start_time_string = datetime.datetime.now().strftime('%H%M')


def main():
    # Step 1: Delete all existing Facility ID versions
    delete_facilityid_versions(config.edit)

    # Step 2: Clear layers from all edit maps in Pro
    clear_layers_from_map()

    # Iterate through each configured versioned edit procedure
    for parent, filters in config.procedure:
        # Step 3: Obtain tuples of system paths for every fc
        features = find_in_sde(config.read, filters['include'],
                               filters['exclude'])

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
            # non_essentials = [facilityid.isVersioned,
            #                   facilityid.can_gisscr_edit(config.edit)]
            if not all(essentials):
                # TODO: log that the layer does not meet requirements for
                # analysis
                continue

            # Step 4c: Make edits to the version
            editor = Edit(feature)
            authorized = editor.owner in config.auth
            editor.edit_version(authorized)


main()
