import config
from utils.management import (delete_facilityid_versions,
                              clear_layers_from_map, find_in_sde,
                              create_versioned_connection)
from utils.identifier import Identifier
from utils.edit import Edit

# Initialize the logger for this file
log = config.logging.getLogger(__name__)


def main():
    log.info(f"Started by {config.username}...")

    # Step 1: Delete all existing Facility ID versions
    log.info("Deleting old Facility ID versions...")
    delete_facilityid_versions(config.edit)

    # Step 2: Clear layers from all edit maps in Pro
    log.info("Removing layers from maps in the FacilityID Pro project...")
    clear_layers_from_map()

    # Iterate through each configured versioned edit procedure
    for parent, options in config.procedure:
        # Step 3: Obtain tuples of system paths for every fc
        log.info("Evaluating which SDE items to evaluate based on filters...")
        features = find_in_sde(config.read, options['include'],
                               options['exclude'])

        # Step 4: Iterate through each feature
        for feature in features:
            # Step 4a: Initialize an identifier object
            facilityid = Identifier(feature)
            log.info(f"Analyzing {facilityid.feature_name}...")

            # Step 4b: Make preliminary checks before analyzing the feature
            essentials = [facilityid.has_table,
                          facilityid.has_facilityid,
                          facilityid.has_globalid,
                          facilityid.editorTrackingEnabled,
                          facilityid.prefix]
            if not all(essentials):
                log.error(("The layer does not qualify for analysis because "
                          "it is missing essential requirements..."))
                continue

            # Step 4c: Compare Edit object to previous script run
            editor = Edit(feature)
            if editor.equals_previous():
                log.info("No records have been edited since the last run...")
                continue

            # Step 4d: Perform edits
            suffix = options["version_suffix"]
            conn_file = create_versioned_connection(editor, parent, suffix)

            log.info(f"Attempting versioned edits on {editor.feature_name} "
                     f"with prefix {editor.prefix} through a child version of "
                     f"{parent}...")
            editor.edit_version(conn_file)

            # Step 4e: Shelve the edited object for future comparisons
            log.info("Storing table for future comparisons...")
            editor.store_current()

            # Step 4f: Delete object instances from memory
            del editor, facilityid

        # Step 5: Reconcile edits, and post depending on config
        # TODO: Add a reconcile/post flow


main()
