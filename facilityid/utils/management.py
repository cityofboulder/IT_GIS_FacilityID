import os
from arcpy.da import Walk
from arcpy.mp import ArcGISProject
from arcpy import (CreateVersion_management, DeleteVersion_management,
                   ListVersions, CreateDatabaseConnection_management)


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


def create_versioned_connection(client: str, database: str,
                                database_user: str, password: str,
                                version_name: str, parent: str,
                                source_connection: str):
    """Create a version and associated versioned database connection.

    Parameters
    ----------
    client : str
        The database client being used (e.g. ORACLE or SQLSERVER)
    database : str
        The instance of the database to use
    database_user : str
        The connecting user to the database instance
    password : str
        The password for the database user
    version_name : str
        The name of the version
    parent : str
        The parent of the version
    source_connection : str
        The connection file used to create the version
    """

    # Create the version first
    CreateVersion_management(in_workspace=source_connection,
                             parent_version=parent,
                             version_name=version_name,
                             access_permission='PRIVATE')

    full_version_name = f"GISSCR.{version_name}"
    connection_name = f"{version_name}.sde"
    connection_file = os.path.join(os.getcwd(), connection_name)
    if not os.path.exists(connection_file):
        CreateDatabaseConnection_management(out_folder_path=os.getcwd(),
                                            out_name=connection_name,
                                            database_platform=client,  # 'ORACLE'
                                            instance=database,  # 'gisprod2'
                                            account_authentication='DATABASE_AUTH',
                                            username=database_user,  # 'gisscr'
                                            password=password,  # 'gKJTZkCYS937'
                                            version_type='TRANSACTIONAL',
                                            version=full_version_name)


def delete_facilityid_versions(connection: str = None) -> None:
    """Deletes versions created for editing Facility IDs

    Parameters
    ----------
    connection : str
        location of the sde connection file
    """

    del_versions = [v for v in ListVersions(connection) if "FacilityID" in v]
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
