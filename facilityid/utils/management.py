import os
from arcpy.da import Walk
from arcpy.mp import ArcGISProject
from arcpy import DeleteVersion_management, ListVersions

from .identifier import Identifier


# Define globals specific to these functions
aprx_location = "./EditFacilityID.aprx"


def find_in_sde(sde_path: str = None, *args) -> Identifier:
    """ Finds all possible feature classes within the sde connection provided based on a list of pattern matches, and
    returns a list representing that file path broken into [sde, dataset (if it exists), feature class]. For example,
    the requester might only want to find the path of feature classes that contain "wF", "sw", and "Flood". If no
    patterns are provided, the function will return all feature classes in the sde_path.

    :param sde_path: The file path to the sde connection file
    :param args: A list of optional strings to filter the data
    :return: An Identifier object
    """
    walker = Walk(sde_path, ['FeatureDataset', 'FeatureClass'])
    for directory, folders, files in walker:
        items = list()
        for f in files:
            if directory.endswith(".sde"):
                items.append((directory, f))
            else:
                dataset = directory.split(os.sep).pop()
                items.append((directory[:-(1 + len(dataset))], dataset, f))

    if not args or len(args) == 0:  # If no args are given or the list passed to args is empty
        for item in items:
            yield Identifier(item)
    else:  # else, args were provided and the list passed to args is not empty, return filtered
        filtered_items = list(filter(lambda x: any(arg in x for arg in args), items))
        for item in filtered_items:
            yield Identifier(item)

    del walker


def delete_facilityid_versions(connection: str = None) -> None:
    """Deletes versions created for editing Facility IDs

    :param connection: location of the sde connection file
    :return: None
    """
    del_versions = [v for v in ListVersions(connection) if "FacilityID" in v]
    for d in del_versions:
        DeleteVersion_management(connection, d)


# TODO: verify that add_layer_to_map works
def add_layer_to_map(feature_class_name: str = None) -> None:
    """ Adds the input layer to a .aprx Map based on the owner of the data.
    For example, the UTIL.wFitting feature would be added to the "UTIL" map
    in the designated .aprx

    :param feature_class_name: Name of the feature class inside sde
    :return:
    """
    user, fc = feature_class_name.split(".")
    aprx = ArcGISProject(aprx_location)
    user_map = aprx.listMaps("%s" % user)[0]
    user_map.addDataFromPath()  # TODO: add data from the gisscr user
    aprx.save()


def clear_layers_from_map():
    # TODO: Translate this function from Map to Pro
    pass
