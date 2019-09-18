from arcpy import da
from arcpy import DeleteVersion_management


def delete_facilityid_versions(connection: str = None) -> None:
    """Deletes versions created for editing Facility IDs

    :param connection: location of the sde connection file
    :return: None
    """
    del_versions = [v.name for v in da.ListVersions(connection) if "FacilityID" in v.name]
    for d in del_versions:
        DeleteVersion_management(connection, d)
