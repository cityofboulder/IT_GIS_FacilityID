from arcpy import da
from arcpy import DeleteVersion_management


def delete_facilityid_versions(connection: str = None, users: list = None) -> None:
    """Deletes versions created for editing Facility IDs

    :param connection: location of the sde connection file
    :param users: list of users with Facility ID versions
    :return: None
    """
    sde_versions = [v.name for v in da.ListVersions(connection)]
    for u in users:
        delete_version = "%s%s" % (u, "_FacilityID")
        if delete_version in sde_versions:
            DeleteVersion_management(connection, delete_version)
