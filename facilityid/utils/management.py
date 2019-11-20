import os
import config
from arcpy.da import Walk
from arcpy.mp import ArcGISProject
from arcpy import (CreateVersion_management, DeleteVersion_management,
                   ListVersions, CreateDatabaseConnection_management,
                   ReconcileVersions_management)

from .edit import Edit

# Initialize the logger for this file
log = config.logging.getLogger(__name__)

# Define globals specific to these functions
aprx_location = "./EditFacilityID.aprx"


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


def versioned_connection(edit_obj: Edit, parent: str, version_name: str):
    """Create a version and associated versioned database connection.

    Parameters
    ----------
    edit_obj : Edit
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
        conn_file = os.path.join(os.getcwd, f"{version_name}.sde")
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
            connect = {"out_folder_path": os.getcwd(),
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


def reconcile_post(parent: str, version: str):
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
                            "with_delete": True}

    ReconcileVersions_management(**reconcile_kwargs)


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


# TODO: verify that add_layer_to_map works
def add_layer_to_map(feature_class_name: str = None) -> None:
    """ Adds the input layer to a .aprx Map based on the owner of the
    data.  For example, the UTIL.wFitting feature would be added to the
    "UTIL" map of the designated .aprx file

    Parameters
    ----------
    feature_class_name : str
        The full name of the feature class inside sde (e.g. UTIL.wFitting)
    """

    user, fc = feature_class_name.split(".")
    aprx = ArcGISProject(aprx_location)
    user_map = aprx.listMaps(f"{user}")[0]
    user_map.addDataFromPath()  # TODO: add data from the gisscr user
    aprx.save()


def clear_layers_from_map():
    # TODO: Translate this function from Map to Pro
    pass


def count(obj):
    def wrapper(*args):
        wrapper.records += 1
        return obj(*args)
    wrapper.records = 0
    return wrapper
