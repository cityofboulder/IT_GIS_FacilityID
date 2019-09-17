# TODO: place globals into yml config file
# TODO: transfer items from personal modules into a project utilities module
# TODO: figure out how to download the boulder_gis package into conda env
import json
import getpass
from datetime import datetime

"""Read in config.json and assign values to variables"""
with open('config.json') as config_file:
    configs = json.load(config_file)
# Boolean for scripted post control
post_control = configs["post_edits"]
# Tags designating how to check IDs
scan_mode = [k for k, v in configs["mode"].items() if v]
# SDE database connection file locations
read_connection = configs["sde"]["read"]
edit_connection = configs["sde"]["edit"]
# Designate which users to check IDs for
users_to_check = configs["users"] if "scan_by_user" in scan_mode else None
# Designate which data sets to check IDs for
dsets_to_check = configs["dsets"] if "scan_by_dset" in scan_mode else None
# Designate which features to check IDs for
feats_to_check = configs["feats"] if "scan_by_feat" in scan_mode else None
# Define what a row in the sde checklist looks like
checklist_row = configs["checklist"]
# Define what a row in the edit summary looks like
edit_counts_row = configs["count"]

"""Define variables that are constant throughout the script"""
# User who initiated the script
username = getpass.getuser()
# Day and time script was run
start_date_string = datetime.now().strftime("%Y%m%d")
start_time_string = datetime.now().strftime('%H%M')



def main():
    """
    The main function of the facility id checker.
    :return:
    """
    pass
