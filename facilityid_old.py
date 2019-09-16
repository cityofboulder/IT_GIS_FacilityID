"""
Author: Jesse Nestler
Date Created: 6/25/18
Purpose: Update the Facility IDs of utility assets that participate in live
Beehive push/pull. Check for duplicate/missing IDs, as well as unique prefixes
between layers.
"""

"""
*******************************************************************************
IMPORT LIBRARIES
*******************************************************************************
"""
global summary, user, v, versioning, tot_edits, fc_edit_count, mins, secs
# standard libraries
import subprocess
import sys
import os
import getpass
import datetime
import time
import traceback
from os import path
import pandas as pd

# third party libraries
import arcpy
from arcpy import env
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEBase import MIMEBase
from email import Encoders

# Arc 10.6 or 10.4?
arc_vers = "10.6" if any("10.6" in f for f in os.listdir("C:\Python27")) else "10.4"

# personal modules
paths = ["S:\PW\PWShare\GIS\Scripts\Modules", 
         path.join("C:\Python27\ArcGIS"+arc_vers,"Lib\site-packages\boulder_gis")]
for pa in paths:
    if not pa in sys.path:
        sys.path.append(pa)

import useful_script_tools as ust
from boulder_gis import utilities as utils

"""
*******************************************************************************
"""
# local database connections
username = getpass.getuser()
comp_user = path.join('C:\\Users', username)
connect = path.join(comp_user, 'AppData', 'Roaming', 'ESRI', 'Desktop'+arc_vers, 'ArcCatalog')
gis = path.join(connect, 'gis on gisprod2.sde')
gisscr = path.abspath(r"S:\PW\PWShare\GIS\Scripts\dbconnections\gisscr on gisprod2.sde")
"""
*******************************************************************************
"""
# project directory
project_path = path.join(r"\\boulder.local\share", "PW", "PWShare", "GIS", "Scripts", "FacilityID")
# logging directory
log_path = path.join(project_path, "Logs")
# mxd location path
mxd_path = path.join(project_path, "MXDs")
# environment settings
env.overwriteOutput = True
"""
*******************************************************************************
"""
def user_dict():
    """ Defines a dict of user:permission-to-edit pairs. If a user is listed 
    in the dictionary, its layers will be investigated for FacID errors. If 
    it is listed as True, the script will also attempt to create versioned 
    edits
    """
    u = {"UTIL": True,
         "PW": True, 
         "TRANS": True,
         "PARKS": True} 
#         "OSMP": False, 
#         "PLAN": False,
#         "FIRE": False,
#         "IT": False,
#         "CV": False,
#         "FINANCE": False,
#         "POLICE": False}
    
    return u


def checklist():
    """ Defines a checklist for use in logging action items post script-completion
    """
    global fc_str, field_str, vers_str, editor_str, gis_str, privs_str, fill_str, check_str, pfix_str
    fc_str = "0 - FEATURE CLASS" #
    pfix_str = "1 - PREFIX" #
    check_str = "2 - CHECK VERSIONED EDITS" #
    field_str = "3 - ENABLE GLOBALID" #
    vers_str = "4 - REGISTER AS VERSIONED" #
    editor_str = "5 - TURN ON EDITOR TRACKING" #
    gis_str = "6 - RE-ENABLE ACCESS TO GIS USER" #
    privs_str = "7 - GRANT GISSCR USER FULL PRIVILEGES" #
    fill_str = "8 - FILL IN FACILITYID VALUES" #
    
    checklist = {
                fc_str: [],
                pfix_str: [],
                check_str: [],
                field_str: [],
                vers_str: [],
                editor_str: [],
                gis_str: [],
                privs_str: [],
                fill_str: []
            }

    return checklist


def count_dict():
    """ Defines a dict of counts for every kind of FACID edit.
    """
    global pfix_c_str, zeros_c_str, null_c_str, dupid_c_str, dupgeom_c_str, vedit_c_str
    fc_str = "0 - FEATURE CLASS"
    pfix_c_str = "4 - INCORRECT PREFIXES"
    zeros_c_str = "5 - LEADING ZEROS"
    null_c_str = "2 - NULL VALUES"
    dupid_c_str = "3 - DUPLICATE IDS"
    dupgeom_c_str = "6 - DUPLICATE GEOMS"
    vedit_c_str = "1 - VERSIONED EDITS"
    
    count = {
            fc_str: [],
            vedit_c_str: [],
            null_c_str: [],
            dupid_c_str: [],
            pfix_c_str: [],
            zeros_c_str: [],
            dupgeom_c_str: []
            }
    
    return count


def clear_mxd_layers(mxd_list = None):
    """ Removes all layers from each edit mxd.
    
    :param mxd_list: a list of mxd file paths
    """
    for m in mxd_list:
        # define mxd
        mxd = arcpy.mapping.MapDocument(m)
        # find the active data frame inside the mxd
        df = mxd.activeDataFrame
        # delete any layers already inside the df
        for lyr in arcpy.mapping.ListLayers(mxd, "", df):
            arcpy.mapping.RemoveLayer(df, lyr)
        mxd.save()


def add_to_mxd(fc_name = None):
    """ Adds the new layer to an mxd based on the owner of the layer.
    
    :param fc_name: name of the feature class to-be-added
    """
    # define mxd
    mxd = arcpy.mapping.MapDocument(path.join(mxd_path, user + versioning['v_name'] + '.mxd'))
    # find the active data frame inside the mxd
    df = mxd.activeDataFrame
    # create a new layer of the feature class to be edited from the gisscr connection
    if dset:
        fc_gisscr = path.join(gisscr, dset, fc_name)
    else:
        fc_gisscr = path.join(gisscr, fc)
    memory_lyr = arcpy.MakeFeatureLayer_management(fc_gisscr, layer)
    disk_lyr = path.join(mxd_path, layer+'.lyr')
    arcpy.SaveToLayerFile_management(memory_lyr, disk_lyr, "ABSOLUTE")
    new_layer = arcpy.mapping.Layer(disk_lyr)
    # add that layer to the data frame
    arcpy.mapping.AddLayer(df, new_layer, "BOTTOM")
    mxd.save()
    os.remove(disk_lyr)


def join_to_lyr():
    """ Joins a table to an mxd if versioned edits could not be performed. Also 
    hides all fields except FACILITYID, NEW_FACID, and OLD_FACID
    """
    # define mxd
    mxd = arcpy.mapping.MapDocument(path.join(mxd_path, user + versioning['v_name'] + '.mxd'))
    # find the active data frame inside the mxd
    df = mxd.activeDataFrame
    # id the layer
    join_lyr = arcpy.mapping.ListLayers(mxd, layer, df)[0]
    # join to that layer
    arcpy.AddJoin_management(join_lyr, "GLOBALID", table, "GLOBALID")
    mxd.save()


def write_csv(table_dict = None, file_loc = None, index_name = None):
    """ Writes a csv from a dictionary using pandas
    
    :param table_dict: dictionary whose keys specify columns and whose dict values are lists of values
    :param file_loc: the location and name of the csv file to-be-written
    :param index_name: the name of the dictionary key to be used as an index
    """
    # set up the data frame (sort if an index was identified)
    if index_name:
        df = pd.DataFrame.from_dict(table_dict)
        cols = list(df)
        cols.sort(reverse = False)
        cols.insert(0, cols.pop(cols.index(index_name)))
        df = df.ix[:, cols]
        df.sort_values(inplace = True, by = index_name)
    else:
        df = pd.DataFrame.from_dict(table_dict)
    # write to csv
    df.to_csv(file_loc, sep = ',', encoding = 'utf-8')


def write_excel(table_dict = None, file_loc = None, index_name = None):
    """ Writes a specifically formatted excel file from a dict using pandas
    
    :param write_list: a list of (dictionary, sheet name) pairs to add to the workbook
    :param table_dict: dictionary whose keys specify columns and whose values are lists of values
    :param file_loc: the location and name of the csv file to-be-written
    :param index_name: the name of the dictionary key to be used as an index
    ;param tab_name: the name of the excel sheet tab
    """
    # set up the data frame (sort if an index was identified)
    if index_name:
        df = pd.DataFrame.from_dict(table_dict)
        cols = list(df)
        cols.sort(reverse = False)
        cols.insert(0, cols.pop(cols.index(index_name)))
        df = df.ix[:, cols]
        df.sort_values(inplace = True, by = index_name)
    else:
        df = pd.DataFrame.from_dict(table_dict)
    
    # excel writer object to excel
    headers = list(df.columns.values)
    w = pd.ExcelWriter(file_loc, engine = 'xlsxwriter')
    df.to_excel(w, index = False, sheet_name = 'Sheet1')
    
    # create workbook/worksheet
    workbook = w.book
    worksheet = w.sheets['Sheet1']
    
    # formatting
    h = {'align': 'left', 'bold': True, 'valign': 'bottom', 'rotation':45}
    header_format = workbook.add_format(h)
    
    # format headers
    for i in range(0, len(headers)):
       worksheet.write(0, i, headers[i], header_format)
    
    # set index width
    widths = [len(x) for x in table_dict[index_name]]
    max_width = max(widths) + 2 if widths else 30
    worksheet.set_column('A:A', max_width)
    
    # freeze top row
    worksheet.freeze_panes(1,0)
    
    #close book
    workbook.close()


def find_dirs(workspace = None, users = None):
    """
    This funtion finds all possible feature classes and datasets to examine 
    given a list of data owners. This function mostly helps in reducing how 
    many nested loops exist in the main block of code below by packaging lists 
    together.
    
    :param workspace: the top level root workspace (must be SDE)
    :param users: A list of data owners in PROD2 that must be examined
    :return (list): A list detailing owner, dset, and feature class paths
    """
    walk = arcpy.da.Walk(workspace, ['FeatureDataset', 'FeatureClass'])
    for dirpath, dirnames, files in walk:
        for f in files:
            if any(u in f for u in users):
                last = dirpath.split(os.sep).pop()
                if last == 'gis on gisprod2.sde':
                    item = [dirpath, None, f]
                else:
                    item = [dirpath[:-(1 + len(last))], last, f]
                yield item
    del walk


def check_exceptions(excepts = None):
    """
    Determines whether the feature class should be checked based on whether 
    certain reserved words appear in the file path.
    
    :param excepts (list): list of exceptions that cannot be present
    :return (bool): if an exemption is found, returns False, otherwise returns True and sets env.workspace
    """
    if any(y in fc for y in excepts):
        return False
    if dset:
        if any(x in dset for x in excepts):
            return False
        env.workspace = path.join(ws, dset)
        return True
    
    env.workspace = ws
    return True


def verify_fields(fc = None):
    """ Verifies whether a given feature class or table has FACID and GLOBALID fields
    
    :param fc: the name of the feature class being examined (not the file path)
    """
    # Make sure FACID field exists & there are entries to edit
    fields = [f.name for f in arcpy.ListFields(fc) if not f.required]
    try:
        count = int(arcpy.GetCount_management(fc).getOutput(0))
        checklist[gis_str].append("")
        if all(a in fields for a in ['FACILITYID', 'GLOBALID']) and count >= 1:
            return True
        else:
            return False
    except Exception as e:
        if isinstance(e, arcpy.ExecuteError):
            checklist[gis_str].append("X")
            msg = "Some related table or attachment has been deleted and rendered {} un-openable...\n"
            ust.log_time(log, msg.format(fc))
            return False


def prefix(fc = None, exst = None):
    """ Finds the prefix of a layer.
    
    :param fc: the feature class or data item being evaluated
    :param exst: a boolean designating whether the fc has the FACILITYID field
    :return master_pfix: the prefix of the feature class, none if no prefix is detected
    :return filled_vals: a boolean describing whether or not someone needs to attribute the FACILITYID field
    """
    master_pfix = None # assume no prefix exists
    filled_vals = True # assume that the table has values filled in
    if exst:
        p_dict = {}
        pfixs = []
        with arcpy.da.SearchCursor(fc, "FACILITYID") as sCurs:
            for row in sCurs:
                if row[0]: # if the row has a value
                    pfix = "".join([x for x in row[0] if x.isalpha()])
                    if len(pfix) > 0: # if the prefix has alpha chars
                        pfixs.append(pfix)
        
        for p in pfixs:
            if p not in p_dict: # if prefix hasn't been logged, write down the prefix and number of occurences
                p_dict[p] = sum(1 for elem in pfixs if elem == p)
        if len(p_dict) > 0: # if prefixes were logged, the most likely prefix is the one that occurs the most
            master_pfix = str(max(p_dict, key = lambda x: p_dict[x])).upper()
        else:
            filled_vals = False
    
    return master_pfix, filled_vals


def preconditions(fc = None):
    """ Verifies if a feature class or table is eligible to have Facility IDs checked and edited.
        
    """
    global data_type, ultimate_checks, verify, m_pfix
    verify = []
    # check file exemptions (stop checking current data item if false)
    ex_check = check_exceptions(temp_exempts) #returns True if not exempt, else False
    if not ex_check:
        return False
    
    # describe the arc object
    desc = arcpy.Describe(fc)
    
    # check whether item is a feature class or table (stop checking current data item if neither)
    data_type = desc.dataType
    data_check = True if data_type in ['FeatureClass', 'Table'] else False
    if not data_check:
        return False
    
    # check versioning registration (continue either way, this is just descriptive and does not stop the process)
    checklist[fc_str].append(fc)
    checklist[vers_str].append("X" if not desc.isVersioned else "")

    # check that FACILITYID and GLOBALID fields are present (stop checking data item if neither/nor are present)
    field_check = verify_fields(fc) # returns True if FACILITYID and GLOBAlID fields exist, else False
    checklist[field_str].append("X" if not field_check else "")
    verify.append(field_check)
    # extract Prefix and check if any FACILITYIDs have been filled in (stop checking current data item if none exist)
    m_pfix, fill_check = prefix(fc, field_check)
    checklist[pfix_str].append(m_pfix if m_pfix else "-")
    checklist[fill_str].append("X" if not fill_check else "")
    verify.append(fill_check)

    # check data privileges (continue either way)
    try:
        privs = ust.find_privileges(gisscr, user, layer.upper())
    except TypeError:
        privs = {"edit": set()}
    checklist[privs_str].append("X" if not privs['edit'] else "")

    # check that editor tracking is turned on (continue either way)
    checklist[editor_str].append("X" if not desc.editorTrackingEnabled else "")
    
    # if any results are false, then we move to the next data item
    if any(not a for a in verify):
        checklist[check_str].append("")
        return False
    else:
        return True


def extract_facids(fc=None):
    """
    If the feature class has a FACILITYID field, this function will extract
    that information from each entry for transformation purposes.

    :param fc (str): file path to the feature class
    :return (dict): a dictionary of {GUID: [prefix, number] pairs}
    :return (str): the master prefix for the layer
    """
    global shape_type, data_type, zeros_count
    fields = ['GLOBALID', 'FACILITYID', 'CREATED_USER', 'CREATED_DATE',
              'LAST_EDITED_USER', 'LAST_EDITED_DATE']
    
    if data_type == 'FeatureClass':
        fields.append('SHAPE@')
        shape_type = arcpy.Describe(fc).shapeType

    id_dict = {}
    edit_dict = {}
    zeros_count = 0

    # summarize facility ids and global ids
    with arcpy.da.SearchCursor(fc, fields) as sCurs:
        for row in sCurs:
            guid = row[0]
            create_edit_info = [row[2], row[3], row[4], row[5]]
            try:
                edits_req = False
                # separate the row's prefix and id number
                pfix = "".join([x for x in row[1] if x.isalpha()]) # = '' if no alphas
                num_str = row[1][len(pfix):] # = '' if no numbers (this retains leading zeros if an id exists)
                # if no prefix exists
                if len(pfix) == 0:
                    edits_req = True
                    pfix = None
                else:
                    # if the prefix isn't capitalized or not the same as the average prefix of the layer
                    if not pfix.isupper() or pfix != m_pfix:
                        edits_req = True
                # if numbers exist
                if len(num_str) > 0:
                    num = int(num_str) # this gets rid of leading zeros
                    # if leading zeros exist
                    if len(num_str) != len(str(num)):
                        edits_req = True
                        zeros_count += 1
                # if no number exists
                else:
                    edits_req = True
                    num = None

            # if the value of row[1] is None, an exception is raised
            except (ValueError, TypeError):
                edits_req = True
                pfix = num = num_str = None

            # if the object is a feature class (rather than a table, which has no "SHAPE@" field)
            if data_type == 'FeatureClass':
                shape = row[6]
                id_dict[guid] = [create_edit_info, [pfix, num, num_str], shape]
            else:
                id_dict[guid] = [create_edit_info, [pfix, num, num_str]]
            
            # add to edit_dict if edits are required
            if edits_req:
                edit_dict[str(guid)] = [str(row[1])]

    return id_dict, edit_dict


def extract_ids(in_dict = None):
    """
    Finds the unused numbers in Facility IDs of a feature class
    
    :param in_dict (dict): the output dictionary of the extract_facids() func
    :return (list): Two lists of all used and unused ids in descending order
    """
    used_ids = [x[1][1] for x in in_dict.itervalues() if x[1][1] != None]
    min_id = min(used_ids)
    # initiate a try block in case the max id is too large and overflows computer memory
    for max_id in sorted(used_ids, reverse = True):
        try:
            range_set = set(range(min_id, max_id))
            used_set = set(used_ids)
            unused_ids = sorted(list(range_set - used_set), reverse = True)
            break
        except (OverflowError, MemoryError):
            continue
    
    return used_ids, unused_ids


def qc_nulls(in_dict = None, used_ids = None, unused_ids = None, e_dict = None):
    """
    Fills in the Facility IDs of entries that have either no ID number, no 
    prefix, or neither.
    
    :param in_dict (dict): the output dictionary of the extract_facids() func
    :param used_ids (list): the output of the extract_ids() function
    :param unused_ids (list): the second output of the extract_ids() function
    :param e_dict (dict): a dict of GLOBALIDs, old and new FACIDs
    """
    global id_count, pfix_count
    id_count = pfix_count = 0
    for k,v in in_dict.iteritems():
        edits_req = False
        p,i,i_str = v[1]
        # if the entry has no ID number
        if not i in used_ids:
            edits_req = True
            # assign the new id
            if len(unused_ids) > 0:
                i = unused_ids.pop()
            else:
                i = max(used_ids) + 1
            # add new id to list of used ids for later comparisons
            used_ids.append(i)
            id_count += 1

        # if the entry has an incorrect prefix
        if p != m_pfix or p == None:
            edits_req = True
            try:
                if p.isalpha():
                    pfix_count += 1
            except AttributeError:
                pass
        
        # if the entry has an id with leading zeros
        try:
            if len(str(i)) != len(i_str):
                edits_req = True
        except TypeError:
            pass
        
        v[1] = [m_pfix, i]
        # add to dict of edits
        if edits_req:
            e_dict[k].append(m_pfix + str(i))

        
def qc_dupes(in_dict = None, used_ids = None, unused_ids = None, e_dict = None):
    """
    Changes duplicate Facility IDs based on the most recently edited time or 
    the shortest/smallest length/area (depending on geom type)
    
    :param in_dict (dict): the output dictionary of the extract_facids() func
    :param used_ids (list): the output of the extract_ids() func
    :param unused_ids (list): the second output of the extract_ids() func
    :param edit (list): a list of GUIDs that need editing
    :param e_dict (dict): a dict of GLOBALIDs and old and new FACIDs
    """
    global dup_fix_count, dup_del_count, tab_dups, del_dups, final_edits, table, duplicates
    dup_fix_count = 0
    dup_del_count = 0
    if data_type == 'Table':
        pass
    else:
        # create a dictionary of duplicates
        duplicates = {}
        for k,v in in_dict.iteritems():
            p,n = v[1]
            # if there are more than one elements with the same id
            if sum(1 for elem in used_ids if elem == n) > 1:
                d = {"key": k, "geom": v[2], "edit": v[0], "facid_list": v[1]}
                if n in duplicates:
                    duplicates[n].append(d)
                else:
                    duplicates[n] = [d]

        if duplicates:
            # sort lists within duplicates to prioritize FacID edits 
            for k,v in duplicates.iteritems():
                # set up different ways of sorting depending on shape_type
                geom_sort = {"Point": lambda x: x['edit'][1], 
                             "Polyline": lambda x: -x['geom'].length, 
                             "Polygon": lambda x: -x['geom'].area,
                             "Final": lambda x: x['edit'][3]}
                
                # sort first by geometry length/area/create-date, then by edit date
                for sort_func in [shape_type, "Final"]:
                    try:
                        v.sort(key = geom_sort[sort_func])
                    # if geoms have no create date (i=1) or edit date (i=3), these should changed first
                    except TypeError:
                        i = 1 if sort_func == shape_type else 3
                        for item in v:
                            if item['edit'][i] == None:
                                v.append(v.pop(v.index(item)))
                        continue
    
            # take care of duplicates based on the sort above
            del_dups = {"GLOBALID": [], "FACID": [], "REPEAT_INDEX": []}
            for v in duplicates.itervalues():
                # loop through list of duplicates until all dups are qc'd
                while len(v) > 1:
                    # remove the last duplicate entry from the list
                    edits_req = True # assume edits must be done 
                    row = v.pop()
                    key = row['key']
                    p,n = row['facid_list']
        
                    # check if geometries are duplicated
                    for other_row in v:
                        if row['geom'].equals(other_row['geom']):
                            edits_req = False # no edit necessary
                            dup_del_count += 1
                            del_dups["GLOBALID"].append(str(key))
                            del_dups["FACID"].append(p + str(n))
                            del_dups["REPEAT_INDEX"].append(str(dup_del_count))
                            break
        
                    # if there are no duplicate geometries
                    if edits_req:
                        e_dict[str(key)] = [p + str(n)] # add key to the edit dict, with old facid
                        dup_fix_count += 1
                        # assign an ID number from unused IDs if there are any left
                        if len(unused_ids) > 0:
                            i = unused_ids.pop()
                        else:
                            i = max(used_ids) + 1
                        # assign ID
                        in_dict[key][1][1] = i
                        used_ids.append(i)
                        facid = m_pfix + str(i)
                        # add GUID to list of GUIDs needing an edit
                        e_dict[key].append(facid)
    
            if del_dups['GLOBALID']:
                write_csv(del_dups, path.join(tab_path, fc + "_DuplicateGeoms{}_{}.csv".format(start_date, start_time)))

        if e_dict:
            final_edits = {}
            final_edits["GLOBALID"] = list(e_dict.iterkeys())
            final_edits["OLD_FACID"] = [v[0] for v in e_dict.itervalues()]
            final_edits["NEW_FACID"] = [v[1] for v in e_dict.itervalues()]
            table = path.join(tab_path, fc + "_EditSummary{}_{}.csv".format(start_date, start_time))
            write_csv(final_edits, table)


def edit_facid_version(edit_fc_name = None, in_dict = None, edit_guids = None, log_name = None):
    """
    Performs Facility ID edits if any duplicate, null, or incorrect entries 
    were detected.
    
    :param edit_fc_name (str): the feature class being edited
    :param in_dict (dict): the output dictionary of the extract_facids() func
    :param edit_guids (list): a list of GUIDs that need editing
    :param log_name (str): the name of the log being written to
    :return (bool): if versioned edits were performed, returns True, else False
    """
    global fc_edit_count, tot_edits
    # if there are edits to be made
    if edit_guids:
        # summarize edit counts
        tot_edits += len(edits)
        fc_edit_count += 1
        count_summary[fc_str].append(edit_fc_name)
        count_summary[pfix_c_str].append(pfix_count) 
        count_summary[zeros_c_str].append(zeros_count)
        count_summary[null_c_str].append(id_count)
        count_summary[dupid_c_str].append(dup_fix_count)
        count_summary[dupgeom_c_str].append(dup_del_count)

        # add the fc to its proper edit mxd
        v = user + versioning['v_name']
        try:
            add_to_mxd(edit_fc_name)
            ust.log_time(log_name, "The layer has been added to the {} map document...".format(v))
        except arcpy.ExecuteError:
            ust.log_time(log_name, "The layer could not be added to the {} map document...\n".format(v))
            count_summary[vedit_c_str].append("NO")
            return False

        # if the user has authorized versioned edits
        if users[user]:
            try:
                # Create a db connection and version for the user if one does not already exist
                sde_conn_name = user.lower() + versioning["conn_name"]
                sde_file_path = path.join(project_path, '{}.sde'.format(sde_conn_name))
                if not path.exists(sde_file_path):
                    ust.create_version_and_db_connection(project_path, v, 'SDE.DEFAULT', gisscr, sde_conn_name)
                    ust.log_time(log, ("A version and database connection have been created for {}...").format(user))

                # Perform edits through that db connection
                # start edit session
                edit = arcpy.da.Editor(sde_file_path)
                edit.startEditing(False, True)
                edit.startOperation()

                # query only entries that need editing
                query = ", ".join("'{}'".format(x) for x in edit_guids)
                where = "GLOBALID IN ({})".format(query)

                # open an update cursor and perform edits
                fields = ["GLOBALID", "FACILITYID"]
                fc_path = path.join(sde_file_path, dset, edit_fc_name) if dset else path.join(sde_file_path, edit_fc_name)
                with arcpy.da.UpdateCursor(fc_path, fields, where) as uCurs:
                    for row in uCurs:
                        row[1] = "".join(str(x) for x in in_dict[row[0]][1])
                        uCurs.updateRow(row)

                # show that edits were performed in the proper version
                ust.log_time(log_name, "Edits were performed through the {} version...".format(v))
                join_to_lyr()
                ust.log_time(log_name, "A table of changed Facility IDs has been joined to {} in the {} map document...\n".format(fc, v))

                # stop editing and delete edit session
                edit.stopOperation()
                edit.stopEditing(True)
                del edit
                arcpy.ClearWorkspaceCache_management() 

                # log results to various tables
                count_summary[vedit_c_str].append("YES")
                return True

            except RuntimeError:
                # write error to log
                ust.log_time(log, "An error occured, see below:\n")
                msg = "{}\n".format(traceback.format_exc())
                print msg; log.write(msg)
                # make sure edit summaries are logged
                count_summary[vedit_c_str].append("NO")
                ust.log_time(log_name, "Versioned edits could not be performed...")
                join_to_lyr()
                ust.log_time(log_name, "A table of new Facility ID values has been joined to {} in the {} map document...\n".format(fc, v))
                return False
        else:
            count_summary[vedit_c_str].append("NO")
            ust.log_time(log, "Versioned edits were not performed...\n")
            return False
    else:
        ust.log_time(log, "No edits needed to be performed...\n")
        return False


def email(attachments = None):
    """
    Used to send email notification (encoded in HTML) of success or failure of the process.
    
    :param attachments (list or str): the files to attach
    :return: {none} sends an email
    """
    # today
    global today
    today = datetime.datetime.today().strftime("%A, %d %B %Y at %H:%M")
    
    # from/to addresses
    sender = 'noreply@bouldercolorado.gov'
    password = utils.forcode('noreply', '\xa1\xe0\xbb\xcf\xdb\xd4\xaa\x97\xe5\xc7', '')
    recipients = ["nestlerj@bouldercolorado.gov",
                  "jeffreyb@bouldercolorado.gov",
                  "salmone@bouldercolorado.gov", 
                  "gregoryk@bouldercolorado.gov", 
                  "simpsonj@bouldercolorado.gov",
                  "spielmanc@bouldercolorado.gov"]
    
    # message
    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = "; ".join(recipients)
    msg['Subject'] = "Facility ID Script Results"
    
    # body
    if not tot_edits:
        body =  """\
            <html>
                <head></head>
                <body>
                    <p>
                    Dear Human,<br><br>
                    There were absolutely no Facility IDs identified for edits 
                    in the entire SDE. That's freakin' amazing! Way to crush your 
                    job.
                    </p>
                    <p>
                    Beep Boop Beep,<br><br>
                    End Transmision
                    </p>
                </body>
            </html>
            """
    else:
        body =  """\
                <html>
                    <head></head>
                    <body>
                        <p>
                        Dear Human,<br><br>
                        Facility IDs were checked on {date}. See attachments 
                        to figure out which layers need modifications and how 
                        to inspect/post the automated edits.
                        </p>
                        <p>
                        If the attachments show that edits were necessary to 
                        one of your layers, please navigate to your mxd linked 
                        below and facilitate (heh) the change:<br><br>
                        <a href="{osmp}">OSMP</a><br>
                        <a href="{parks}">PARKS</a><br>
                        <a href="{plan}">PLAN</a><br>
                        <a href="{popo}">POLICE</a><br>
                        <a href="{pw}">PW</a><br>
                        <a href="{trans}">TRANS</a><br>
                        <a href="{util}">UTIL</a>
                        </p>
                        <p>
                        A total of {e_count} IDs in {fc} features 
                        were identified for edits in {m} minutes and {s} seconds.
                        </p>
                        <p>
                        Beep Boop Beep,<br><br>
                        End Transmision
                        </p>
                    </body>
                </html>
                """.format(date = today, e_count = str(tot_edits), 
                           fc = str(fc_edit_count), m = mins, s = secs, 
                           osmp = path.join(mxd_path, "OSMP_FacilityID.mxd"),
                           parks = path.join(mxd_path, "PARKS_FacilityID.mxd"),
                           plan = path.join(mxd_path, "PLAN_FacilityID.mxd"),
                           popo = path.join(mxd_path, "POLICE_FacilityID.mxd"),
                           pw = path.join(mxd_path, "PW_FacilityID.mxd"),
                           trans = path.join(mxd_path, "TRANS_FacilityID.mxd"),
                           util = path.join(mxd_path, "UTIL_FacilityID.mxd"))
        if attachments:
            for item in attachments:
                a = open(item, 'rb')
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(a.read())
                Encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment', filename=item.split(os.sep).pop())
                msg.attach(part)

    msg.attach(MIMEText(body, 'html'))
    
    # create SMTP object
    server = smtplib.SMTP(host = 'smtp.office365.com', port = 587)
    server.ehlo()
    server.starttls()
    server.ehlo()
    
    # log in
    server.login(sender, password)
    
    # send email
    server.sendmail(sender, recipients, msg.as_string())
    server.quit()


"""
*******************************************************************************
"""
if __name__ == '__main__':
    # logging setup
    start = time.time()
    d_start = datetime.datetime.now()
    start_date = d_start.strftime("%Y%m%d")
    start_time = d_start.strftime('%H%M')

    # create a folder for log materials
    log_day_path = path.join(log_path, "LogsFrom{}".format(start_date))
    tab_path = path.join(log_day_path, 'JoinTables{}_{}'.format(start_date, start_time))
    if not path.exists(log_day_path):
        os.mkdir(log_day_path)
    os.mkdir(tab_path)

    # create file names
    log_name = path.join(log_day_path, 'ProcessLog{}_{}.txt'.format(start_date, start_time))
    checklist_file = path.join(log_day_path, 'SDEActionItems{}_{}.xlsx'.format(start_date, start_time))
    edit_summary_file = path.join(log_day_path, "EditSummary{}_{}.xlsx".format(start_date, start_time))
    howto_file = path.join(log_path, "AttachmentExplanation.docx")

    # summary table set-up
    count_summary = count_dict()
    checklist = checklist()

    # open log as a file object
    log = open(log_name, 'w')

    """
    ***************************************************************************
    START SCRIPT
    ***************************************************************************
    """
    try:
        ust.log_time(log, "Started by {}...".format(getpass.getuser()))
        """
        ***********************************************************************
        """
        # Delete versions if previously created
        users = user_dict()
        versioning = {"v_name": "_FacilityID", "parent": "_LIVE", "conn_name": "_facid"}
        sde_versions = [v.name for v in arcpy.da.ListVersions(gisscr)]
        for k in users.iterkeys():
            delete_version = "{}{}".format(k, versioning['v_name'])
            if delete_version in sde_versions:
                arcpy.DeleteVersion_management(gisscr, delete_version)
        ust.log_time(log, "All necessary versions have been deleted...\n")
        
        # Clear layers from all edit mxds
        mxds = [path.join(mxd_path, m) for m in os.listdir(mxd_path) if 'mxd' in m]
        clear_mxd_layers(mxds)
        ust.log_time(log, "Edit MXDs have been cleared of all layers...\n")

        # Find all assets with these users, and edit only if they are set to True
        temp_exempts = ["_", "NETWORK", "Topology", "ssTap", "PavementMaintenance"]
        path_gener = find_dirs(gis, [u for u in users.iterkeys()])
        
        # Start tracking edit counts
        fc_edit_count = 0
        tot_edits = 0
        
        # Iterate through every asset feature class
        for p in path_gener:
            # Define variables
            ws, dset, fc = p
            # Get user and layer name
            user, layer = fc.split('.')
            
            # Step 1: Perform various checks and log them to the action items
            check = preconditions(fc)
            if not check:
                continue

            # Step 2: Extract FACIDs and list out edits
            ust.log_time(log, ("Examining {} with prefix {}...").format(fc, m_pfix))
            id_dict, edits = extract_facids(fc)

            # Step 3: Summarize id numbers
            used, unused = extract_ids(id_dict)

            # Step 4: Get rid of null values in FacIDs
            qc_nulls(id_dict, used, unused, edits)

            # Step 5: Eliminate duplicate IDs (table duplicates are not QCd)
            qc_dupes(id_dict, used, unused, edits)

            # Step 6: Edit the feature class
            guids = list(edits.iterkeys())
            check3 = edit_facid_version(fc, id_dict, guids, log)
            checklist[check_str].append("X" if check3 else "")
            if not check3:
                continue

        # Step 7: Write final times and counts to log
        total = time.time() - start
        mins = str(int((total)/60))
        secs = str(int(round((total)%60,0)))
        ust.log_time(log, ("A total of {} entries in {} features were identified for edits in {} minutes and {} seconds").format(str(tot_edits), str(fc_edit_count), mins, secs))
        
        # Step 8: Write files and send email with attachments
        for d,f in [(count_summary, edit_summary_file), (checklist, checklist_file)]:
            write_excel(d, f, fc_str)

        email([howto_file, checklist_file, edit_summary_file])

    except Exception as e:
        # catch unknown exception and write to log
        ust.log_time(log, "An error occured, see below:\n")
        msg = "{}\n".format(traceback.format_exc())
        print msg; log.write(msg)
        # send email notification of script failure
        r = "{}@bouldercolorado.gov".format(username)
        s = "An error halted the Facility ID script"
        m = """The following error halted the Facility ID script from running to completion:<br><br>
               {e}<br><br>
               Please navigate to the script <a href="{f}">here</a> to make the necessary changes and re-run.<br><br>
            """.format(e = traceback.format_exc(), f = project_path, layer = fc)
        ust.email(s, m, r)

    finally:
        # write list of dependencies to requirements txt file
        deps = subprocess.check_output([sys.executable, "-m", "pip", "freeze"]).split("\r")
        with open(path.join(project_path, 'requirements.txt'), 'w') as f_:
            for entry in deps:
                f_.write(entry)
        
        # delete db connection
        for u in users.iterkeys():
            t = path.join(project_path, u.lower() + versioning["conn_name"] + '.sde')
            if path.exists(t):
                os.remove(t)

        # close the log
        log.close()
        del log
