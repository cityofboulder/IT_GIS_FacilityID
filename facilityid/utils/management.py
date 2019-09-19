from arcpy import da
from arcpy import mp
from arcpy import DeleteVersion_management


def delete_facilityid_versions(connection: str = None) -> None:
    """Deletes versions created for editing Facility IDs

    :param connection: location of the sde connection file
    :return: None
    """
    del_versions = [v.name for v in da.ListVersions(connection) if "FacilityID" in v.name]
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
    aprx_location = "./EditFacilityID.aprx"
    aprx = mp.ArcGISProject(aprx_location)
    user_map = aprx.listMaps("%s" % user)[0]
    user_map.addDataFromPath() # TODO: add data from the gisscr user
