import csv
import os

import facilityid.config as config
from arcpy import (CreateDatabaseConnection_management,
                   CreateVersion_management, DeleteVersion_management,
                   ExecuteError, ListVersions, ReconcileVersions_management)
from arcpy.da import Walk
from arcpy.mp import ArcGISProject

# Initialize the logger for this file
log = config.logging.getLogger(__name__)


def find_in_sde(sde_path: str, includes: list = [], excludes: list = []):
    """Finds all possible feature classes within the sde connection
    provided,  based on lists of pattern matches.

   If no patterns are provided, the function will return all feature
   classes in the sde_path.

    Parameters
    ----------
    sde_path : str
        The file path to the sde connection file
    includes : list, optional
        A list of optional strings that all output must contain, by
        default []
    excludes : list, optional
        A list of optional strings that all output cannot contain, by
        default []

    Returns
    -------
    list
        Tuples representing (sde, dataset, feature) or (sde, feature)
    """

    walker = Walk(sde_path, ['FeatureDataset', 'FeatureClass'])
    items = list()
    for directory, _, files in walker:
        for f in files:
            if directory.endswith(".sde"):
                items.append((directory, f))
            else:
                root = os.path.dirname(directory)
                dataset = os.path.basename(directory)
                items.append((root, dataset, f))
    del walker

    # Make sure that the output includes or excludes the keywords provided at
    # function call
    assert set(includes).isdisjoint(set(excludes))
    if includes:
        items = [i for i in items if any(
            arg.lower() in os.path.join(*i).lower() for arg in includes)]
    if excludes:
        items = [i for i in items if not any(
            arg.lower() in os.path.join(*i).lower() for arg in excludes)]

    items.sort(key=lambda x: x[-1])
    return items


def versioned_connection(edit_obj, parent: str, version_name: str):
    """Create a version and associated versioned database connection.

    Parameters
    ----------
    edit_obj : Edit object
        The Edit object of the feature class being analyzed
    parent : str
        The parent of the edit version to be created
    version_name : str
        The name of the version to be created

    Returns
    -------
    str
        A file path to the proper connection file, or an empty string if
        versioned edits cannot be performed.
    """

    authorized = edit_obj.owner in config.auth
    version_essentials = [authorized,
                          edit_obj.isVersioned,
                          edit_obj.can_gisscr_edit(config.edit)]
    if all(version_essentials):
        conn_file = os.path.join(".\\.esri", f"{version_name}.sde")
        version_owner = "GISSCR"
        full_version_name = f"{version_owner}.{version_name}"
        if os.path.exists(conn_file):
            log.debug(f"{version_name} has already been created...")
        else:
            # Create the version
            log.debug((f"Creating a version called {version_name} owned by "
                       f"{version_owner}..."))
            version = {"in_workspace": config.edit,
                       "parent_version": parent,
                       "version_name": version_name,
                       "access_permission": "PRIVATE"}
            CreateVersion_management(**version)

            # Create the database connection file
            log.debug(f"Creating a versioned db connection at {conn_file}...")
            connect = {"out_folder_path": ".\\.esri",
                       "out_name": f"{version_name}.sde",
                       "version": full_version_name,
                       **config.db_params}
            CreateDatabaseConnection_management(**connect)

        return conn_file

    else:
        # Logging to understand why the layer cannot be edited in a version
        if not version_essentials[0]:
            log.error("Edits are not authorized by the data owner...")
        if not version_essentials[1]:
            log.error("The layer is not registered as versioned...")
        if not version_essentials[2]:
            log.error("The layer is not editable by the GISSCR user...")

        return ""


def reconcile_post(parent: str, version: str) -> dict:
    """Reconciles a version. Posts the result to parent if configured.

    Parameters
    ----------
    parent : str
        The name of the parent version
    version : str
        The name of the version to be reconciled

    Returns
    -------
    dict
        A dictionary of parent : success/failure of version post
    """

    rec_post_log = dict()
    reconcile_kwargs = {"input_database": config.edit,
                        "reconcile_mode": "ALL_VERSIONS",
                        "target_version": parent,
                        "edit_versions": version,
                        "abort_if_conflicts": True,
                        "conflict_definition": "BY_OBJECT"}
    if config.post_edits:
        reconcile_kwargs = {**reconcile_kwargs,
                            "acquire_locks": True,
                            "with_post": True,
                            "with_delete": False}

    try:
        log.info(f"Reconciling {version} against {parent}...")
        ReconcileVersions_management(**reconcile_kwargs)
        if config.post_edits:
            rec_post_log[parent] = True
        else:
            rec_post_log[parent] = False
    except ExecuteError:
        log.exception("Could not reconcile and post...")
        rec_post_log[parent] = False

    return rec_post_log


def delete_facilityid_versions(connection: str) -> None:
    """Deletes versions created for editing Facility IDs

    Parameters
    ----------
    connection : str
        location of the sde connection file
    """

    del_versions = [v for v in ListVersions(
        connection) if "FACILITYID" in v.upper()]
    for d in del_versions:
        DeleteVersion_management(connection, d)


def clear_map_layers():
    """Removes layers from maps within the ArcGIS Pro project template.
    Does not remove the layers if they are group layers or basemaps.
    """
    aprx = ArcGISProject(config.aprx)
    for map_ in aprx.listMaps():
        del_layers = [x for x in map_.listLayers(
        ) if not x.isGroupLayer and not x.isBasemapLayer]
        if del_layers:
            for d in del_layers:
                map_.removeLayer(d)


def save_layer_files():
    """Saves layers in every map to a layer file based on user. If a
    group layer does not exist, it will save an individual layer file
    for every layer that needs edits. Saved in the .esri folder of the
    project.
    """
    aprx = ArcGISProject(config.aprx)
    for map_ in aprx.listMaps():
        try:
            layer = [x for x in map_.listLayers() if x.isGroupLayer][0]
            layer.saveACopy(f".\\.esri\\{map_.name}_FeaturesToEdit.lyrx")
        except IndexError:
            log.exception(f"No group layers exist in the {map_.name} map...")
            layers = [x for x in map_.listLayers() if not x.isBasemapLayer]
            for l in layers:
                l.saveACopy(f".\\.esri\\{l.name}.lyrx")


def write_to_csv(csv_file: str, rows: list):
    """Write dict-like rows to a csv file. Append if the file exists,
    create a new file if it does not already exist.

    Parameters
    ----------
    csv_file : str
        File path to the csv file
    rows : list
        Each item in the list is a dictionary representing a row
    """
    fields = list(rows[0].keys())
    if not os.path.exists(csv_file):
        with open(csv_file, 'w', newline='') as c:
            writer = csv.DictWriter(c, fieldnames=fields)
            writer.writeheader()
    with open(csv_file, 'a', newline='') as c:
        writer = csv.DictWriter(c, fieldnames=fields)
        for row in rows:
            writer.writerow(row)


def remove_files(include: list, exclude: list = []):
    """Removes files from their directories based on filters provided.

    Parameters
    ----------
    include : list
        If any string keyword in args appears in the file name, it will
        be deleted
    exclude : list
        If any keyword in this parameter appears in the file name, it
        will not be deleted
    """
    del_files = list()
    for root, _, files in os.walk(os.getcwd()):
        for f in files:
            if any(arg in f for arg in include) and all(
                   arg not in f for arg in exclude):
                del_files.append(os.path.join(root, f))

    if del_files:
        for d in del_files:
            os.remove(d)


def _email_body(user: str, edited_users: list, success: dict) -> str:
    """Defines the main body of the email sent at the end of the script.

    Parameters:
    -----------
    user : str
        The user email being sent
    edited_users : list
        All users that have edited layers
    success : dict
        Boolean values for each parent version describing whether
        versions have been successfully posted.

    Returns:
    --------
    str
        A str with HTML tags that makes up the main body of the email
    """

    if user in edited_users:
        if config.post_edits:
            if all(success.values()):
                insert = ("Versioned edits to Facility IDs have been posted "
                          "on your behalf by the GISSCR user.")
            else:
                insert = ("The GISSCR user attempted to post Facility ID "
                          "edits on your behalf, but encountered "
                          "errors while posting one or more of the child "
                          "versions .<br><br>"
                          "A layer file with versioned connections to your "
                          "data has been attached to this email for you to "
                          "post manually.")
        else:
            insert = (" Versioned edits to Facility IDs have been performed "
                      "on your behalf by the GISSCR user.<br><br>"
                      "Please navigate to your department's attached layer "
                      "file to inspect the versioned edits and post all "
                      "changes.<br><br>"
                      "If you have not authorized edits, registered your data "
                      "as versioned, or granted GISSCR edit access to your "
                      "data, your department's layer file contains read-only "
                      "layers joined to a table of edits. You can manually "
                      "change sources for each layer and perform the edits "
                      "yourself.")
    else:
        insert = (f"None of the features owned by {user} required Facility ID "
                  "edits. Congratulations!")

    body = f"""\
                <html>
                    <head></head>
                    <body>
                        <p>
                        Dear Human,<br><br>
                        {insert}
                        </p>
                        <p>
                        Beep Boop Beep,<br><br>
                        End Transmission
                        </p>
                    </body>
                </html>
                """
    return body


def send_email(user: str, edited_users: list, success: dict, recipients: list,
               *attachments):
    import smtplib
    from email.MIMEMultipart import MIMEMultipart
    from email.MIMEText import MIMEText
    from email.MIMEBase import MIMEBase
    from email import Encoders
    # from/to addresses
    sender = 'noreply@bouldercolorado.gov'
    password = "3qIjkh1)vU"

    # message
    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = "; ".join(recipients)
    msg['Subject'] = "Facility ID"

    # body
    body = _email_body(user, edited_users, success)
    if attachments:
        for item in attachments:
            a = open(item, 'rb')
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(a.read())
            Encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment',
                            filename=item.split(os.sep).pop())
            msg.attach(part)

    msg.attach(MIMEText(body, 'html'))

    # create SMTP object
    server = smtplib.SMTP(host='smtp.office365.com', port=587)
    server.ehlo()
    server.starttls()
    server.ehlo()

    # log in
    server.login(sender, password)

    # send email
    server.sendmail(sender, recipients, msg.as_string())
    server.quit()
