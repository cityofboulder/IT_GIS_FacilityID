import config
from utils.management import (delete_facilityid_versions,
                              clear_layers_from_map, find_in_sde,
                              versioned_connection, reconcile_post)
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

            # Step 4d: Create versioned connection, if applicable
            suffix = options["version_suffix"]
            version_name = f"{editor.user}{suffix}"
            conn_file = versioned_connection(editor, parent, version_name)

            # Step 4e: Perform edits
            log.info((f"Attempting versioned edits on {editor.feature_name} "
                     f"with prefix {editor.prefix}..."))
            editor.edit_version(conn_file)

            # Step 4f: Shelve the edited object for future comparisons
            log.info("Storing table for future comparisons...")
            editor.store_current()

            # Step 4g: Delete object instances from memory
            del editor, facilityid

        # Step 5: Reconcile edits, and post depending on config
        log.info(f"Reconciling {version_name} against {parent}...")
        reconcile_post(parent, version_name)

    # Step 6: Summarize counts
    log.info(f"The script inspected {Identifier.records} features "
             f"and edited {Edit.records} of them...")


main()
