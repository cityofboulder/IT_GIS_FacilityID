import csv
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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


def versioned_connection(parent: str, version_name: str):
    """Create a version and associated versioned database connection.

    Parameters
    ----------
    parent : str
        The parent of the edit version to be created
    version_name : str
        The name of the version to be created

    Returns
    -------
    str
        A file path to the proper connection file
    """

    conn_file = os.path.join(".\\.esri", f"{version_name}.sde")
    full_conn_path = os.path.realpath(conn_file)

    if os.path.exists(conn_file):
        log.debug(f"{version_name} has already been created...")
    else:
        version_owner = "GISSCR"
        full_version_name = f"{version_owner}.{version_name}"

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

    return full_conn_path


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
        A dictionary of version:(success/failure of version post) pairs
    """

    post_kwargs = {"input_database": config.edit,
                   "reconcile_mode": "ALL_VERSIONS",
                   "target_version": parent,
                   "edit_versions": version,
                   "abort_if_conflicts": True,
                   "conflict_definition": "BY_OBJECT",
                   "acquire_locks": True,
                   "with_post": True,
                   "with_delete": False}

    try:
        log.info(f"Posting edits in {version} to {parent}...")
        ReconcileVersions_management(**post_kwargs)
        return True
    except ExecuteError:
        log.exception("Could not reconcile and post...")
        return False


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
    aprx.save()


def save_layer_file(user: str, lyr_file_name: str):
    """Saves a layer file based on the user and version name.

    Parameters
    ----------
    user : str
        The user whose map contains the specified layer file
    lyr_file_name : str
        The name of the layer file that needs to be saved
    """

    aprx = ArcGISProject(config.aprx)
    user_map = aprx.listMaps(user)[0]
    lyr = user_map.listLayers(lyr_file_name)[0]
    lyr.saveACopy(f".\\.esri\\{lyr_file_name}.lyrx")


def post_and_save_layer_files(user: str, version_info: dict):

    for version, info in version_info.items():
        if user in config.post_edits:
            succeeded = reconcile_post(info["parent"], version)
            if succeeded:
                info["posted"] = True
        else:
            if user in config.versioned_edits or not info["posted"]:
                log.info(f"Saving layer file for {version}...")
                save_layer_file(user, version)


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


def list_files(include: list, exclude: list = [], delete: bool = False):
    """Lists files from the package's root directory based on the
    filters provided in the positional args.

    Parameters
    ----------
    include : list
        If any string keyword in this parameter appears in the file
        name, it will be added to the list
    exclude : list
        If any keyword in this parameter appears in the file name, it
        will not be added to the list
    delete : bool
        A trigger to delete the files listed

    Returns:
    --------
    list
        A list of system paths to the files that match the spec'd
        criteria. If the delete flag is raised, an empty list is
        returned
    """
    listed = list()
    for root, _, files in os.walk(os.getcwd()):
        for f in files:
            if any(arg in f for arg in include) and all(
                   arg not in f for arg in exclude):
                listed.append(os.path.join(root, f))

    if delete:
        for d in listed:
            os.remove(d)
    else:
        return listed


def create_html_table(data: list) -> str:
    """Creates table encoded in HTML, where columns are sorted based on
    the column names of each dict key.

    Parameters
    ----------
    data : list
        A list of dicts, where each dict has "col_name": value pairs

    Returns
    -------
    str
        A table coded with HTML tags
    """

    # Encode headers into HTML
    sorted_headers = sorted(data[0])
    headers = "".join([f"<th>{x}</th>" for x in sorted_headers])
    header_row = f"<tr>{headers}</tr>"

    # Encode table data
    table_data = ""
    for dict_row in data:
        sorted_data = [dict_row[x] for x in sorted_headers]
        row_data = "".join([f"<td>{x}</td>" for x in sorted_data])
        table_row = f"<tr>{row_data}</tr>"
        table_data += table_row

    # Combine into a single table
    table = f"<table>{header_row}{table_data}</table>"

    return table


def email_matter(user: str, posted_successfully: list, attach_list: list,
                 failed_inspection: list, failed_versioning: list,
                 counts: list):
    """Defines the main body of the email sent at the end of the script,
    and also returns attachments

    Parameters:
    -----------
    user : str
        The data owner being emailed
    posted_successfully : list
        A list of bools for whether all versions posted successfully
    attach_list : list
        List of all files that might need to be emailed
    failed_inspection : list
        A list of dicts, derived from the Identifier class
    failed_versioning : list
        A list of dicts, derived from the Edit class
    counts : list
        A list of dicts, derived from the Edit class, detailing number
        of edits performed on any layer that was edited

    Returns:
    --------
    str
        A str with HTML tags that makes up the main body of the email
    list
        A list of system paths to files that need to be attached to the
        email
    """

    attach = []
    if user in config.versioned_edits:
        if posted_successfully and all(posted_successfully):
            insert = ("Versioned edits to Facility IDs "
                      "have been posted on your behalf."
                      "\N{Fire} \N{Fire} \N{Fire}")
        else:
            insert = ("Versioned edits were attempted on your behalf. Any "
                      "versions that were not posted automatically are "
                      "attached as one or more layer files. Open those layer "
                      "files and reconcile/post the changes.")
            attach = [x for x in attach_list if user in x and '.lyrx' in x]
    else:
        insert = ("You have not authorized versioned edits, but your data had "
                  "irregular Facility IDs. Use the attached csv files to edit "
                  "your data.")
        attach = [x for x in attach_list if user in x and '.csv' in x]

    if counts:
        user_counts = [x for x in counts if user in x["0 - Feature"]]
        if user_counts:
            insert += ("<br><br>"
                       f"Here is a breakdown of edits performed on {user} "
                       "layers:"
                       "<br><br>")
            insert += create_html_table(user_counts)

    if failed_inspection:
        user_fail = [x for x in failed_inspection if user in x["0 - Feature"]]
        if user_fail:
            insert += ("<br><br>"
                       "The following features could not be scanned for "
                       "incorrect Facility IDs. If you restore each feature "
                       "based on the table below, Facility ID checks will be "
                       "re-enabled."
                       "<br><br>")
            insert += create_html_table(user_fail)

    if failed_versioning:
        user_fail = [x for x in failed_versioning if user in x["0 - Feature"]]
        if user_fail:
            insert += ("<br><br>"
                       "The following features could not be edited in a "
                       "version. If you restore each feature based on the "
                       "table below, the layer will be eligible for versioned "
                       "edits."
                       "<br><br>")
            insert += create_html_table(user_fail)
            attach += [x for x in attach_list if user in x and '.csv' in x]

    body = f"""\
                <html>
                    <head>
                        <style>
                        table {{
                            border-collapse: collapse;
                            border: 1px solid;
                        }}

                        td, th {{
                            border: 1px solid rgb(190,190,190);
                            padding: 10px 10px;
                            letter-spacing: 0.7px;
                        }}

                        td {{
                            text-align: center;
                        }}
                        </style>
                    </head>
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
    return body, attach


def send_email(body: str, recipients: list, *attachments):
    # from/to addresses
    sender = 'noreply@bouldercolorado.gov'
    password = "3qIjkh1)vU"

    # message
    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = "; ".join(recipients)
    msg['Subject'] = "\N{High Voltage Sign} Facility ID \N{High Voltage Sign}"

    if attachments:
        for item in attachments:
            a = open(item, 'rb')
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(a.read())
            encoders.encode_base64(part)
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
