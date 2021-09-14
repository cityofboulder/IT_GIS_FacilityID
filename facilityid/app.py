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
    exclude = ['AllEditsEver', 'GroupLayerTemplate']
    mgmt.list_files(['.sde', '.lyrx', '.csv'], exclude, True)

    # Step 2: Clear layers from all edit maps in Pro
    log.info("Removing layers from maps in the FacilityID Pro project...")
    mgmt.clear_map_layers()

    versions = dict()  # a dict to keep track of all the created versions
    # Iterate through each configured versioned edit procedure
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
            if not facilityid.essentials():
                continue

            # Step 4c: Compare Edit object to previous script run
            editor = edit.Edit(feature)
            if editor.equals_previous():
                log.info(("No records have been edited in "
                          f"{editor.feature_name} since the last run..."))
                continue

            # Step 4d: Check version requirements
            if editor.version_essentials():
                suffix = options["version_suffix"]
                v_name = f"{editor.owner}{suffix}"
                conn_file = mgmt.versioned_connection(parent, v_name)
                if v_name not in versions.keys():
                    versions[v_name] = {"parent": parent, "posted": False}
            else:
                conn_file = ""

            # Step 4e: Perform edits
            log.info((f"Attempting edits on {editor.feature_name} "
                     f"with prefix {editor.prefix}..."))
            editor.edit_version(conn_file)

            # Step 4f: Shelve the edited object for future comparisons
            log.info("Storing table for future comparisons...")
            editor.store_current()

            # Step 4g: Delete object instances from memory
            del editor, facilityid

    # Step 5: Loop through all users that had edits performed
    e_users = edit.Edit.edited_users  # Users that needed edits
    scan_fails = identify.Identifier.failures
    edit_fails = edit.Edit.version_failures
    edit_counts = edit.Edit.edited_features
    for user in identify.Identifier.inspected_users:
        # Step 5a: Post edits or save layer files if they have edits
        post = None
        if user in e_users:
            user_versions = {k: v for k, v in versions.items() if user in k}
            mgmt.post_and_save_layer_files(user, user_versions)
            post = [v["posted"] for v in user_versions.values()]

        # Step 5b: Send an email with results
        all_files = mgmt.list_files(['.csv', '.lyrx'])
        body, files = mgmt.email_matter(
            user, e_users, post, all_files, scan_fails, edit_fails,
            edit_counts)
        mgmt.send_email(body, config.recipients[user], *files)
        log.info(f"Email sent to {user} recipients...")
