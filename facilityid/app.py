import os

import facilityid.config as config
import facilityid.utils.edit as edit
import facilityid.utils.identifier as identify
import facilityid.utils.management as mgmt

# Initialize the logger for this file
log = config.logging.getLogger(__name__)


def main():
    log.info(f"Started by {config.username}...")

    # Step 1: Delete all existing Facility ID versions and old files
    log.info("Deleting old Facility ID versions...")
    mgmt.delete_facilityid_versions(config.edit)
    mgmt.remove_files(['.sde', '.lyrx', '.csv'], ['AllEditsEver'])

    # Step 2: Clear layers from all edit maps in Pro
    log.info("Removing layers from maps in the FacilityID Pro project...")
    mgmt.clear_map_layers()

    # Iterate through each configured versioned edit procedure
    post_success = dict()
    for parent, options in config.procedure.items():
        # Step 3: Obtain tuples of system paths for every fc
        log.info("Evaluating which SDE items to evaluate based on filters...")
        features = mgmt.find_in_sde(config.read, options['include'],
                                    options['exclude'])

        # Step 4: Iterate through each feature
        for feature in features:
            # Step 4a: Initialize an identifier object
            facilityid = identify.Identifier(feature)
            log.info(f"Analyzing {facilityid.feature_name}...")

            # Step 4b: Make preliminary checks before analyzing the feature
            essentials = [facilityid.has_table,
                          facilityid.has_facilityid,
                          facilityid.has_globalid,
                          facilityid.editorTrackingEnabled,
                          facilityid.prefix]
            if not all(essentials):
                log.error((f"{facilityid.feature_name} does not qualify for "
                           "analysis because it is missing essential "
                           "requirements..."))
                continue

            # Step 4c: Compare Edit object to previous script run
            editor = edit.Edit(feature)
            if editor.equals_previous():
                log.info(("No records have been edited in "
                          f"{editor.feature_name} since the last run..."))
                continue

            # Step 4d: Create versioned connection, if applicable
            suffix = options["version_suffix"]
            version_name = f"{editor.owner}{suffix}"
            conn_file = mgmt.versioned_connection(editor, parent, version_name)

            # Step 4e: Perform edits
            log.info((f"Attempting versioned edits on {editor.feature_name} "
                     f"with prefix {editor.prefix}..."))
            editor.edit_version(conn_file)

            # Step 4f: Shelve the edited object for future comparisons
            log.info("Storing table for future comparisons...")
            editor.store_current()

            # Step 4g: Delete object instances from memory
            del editor, facilityid

        # Step 5: Reconcile edit version (and post, depending on config)
        if conn_file:
            post_status = mgmt.reconcile_post(parent, version_name)
            post_success = {**post_success, **post_status}

    # Step 6: Save layer files if posts were not authorized or completed
    log.info("Saving layer files...")
    if not config.post_edits or any(not x for x in post_success.values()):
        mgmt.save_layer_files()

    # Step 7: Send an email with results
    esri = r".\\.esri"
    layer_files = [os.path.join(esri, f)
                   for f in os.listdir(esri) if f.endswith('.lyrx')]
    for user, stewards in config.recipients:
        mgmt.send_email(user, edit.Edit.edited_users, post_success, stewards,
                        r".\\facilityid\\log\\facilityid.log",
                        r".\\facilityid\\log\\AllEditsEver.csv",
                        *[x for x in layer_files if user in x])
