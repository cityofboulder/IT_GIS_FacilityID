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
            log.info((f"Attempting versioned edits on {editor.feature_name} "
                     f"with prefix {editor.prefix}..."))
            editor.edit_version(conn_file)

            # Step 4f: Shelve the edited object for future comparisons
            log.info("Storing table for future comparisons...")
            editor.store_current()

            # Step 4g: Delete object instances from memory
            del editor, facilityid

    # Step 5: Email users that were inspected but did not need edits
    i_users = identify.Identifier.inspected_users  # Users that were inspected
    e_users = edit.Edit.edited_users  # Users that needed edits
    n_users = list(set(i_users) - set(e_users))  # Inspected users w/ no edits
    for user in n_users:
        body = (f"None of the features owned by {user} required Facility ID "
                "edits. \N{party popper}")
        mgmt.send_email(body, config.recipients[user])

    # Step 6: Loop through all users that had edits performed
    for user in e_users:
        # Step 6a: Post edits or save layer files
        user_versions = {k: v for k, v in versions.items() if user in k}
        for version, info in user_versions.items():
            if user in config.post_edits:
                succeeded = mgmt.reconcile_post(info["parent"], version)
                if succeeded:
                    info["posted"] = True
            else:
                if user in config.versioned_edits or not info["posted"]:
                    log.info("Saving layer files...")
                    mgmt.save_layer_files()

        # Step 6b: Send an email with results
        all_files = mgmt.list_files(['.csv.', '.lyrx'])
        post = [v["posted"] for v in user_versions.values()]
        body, files = mgmt.email_matter(user, post, all_files)
        mgmt.send_email(body, config.recipients[user], *files)
