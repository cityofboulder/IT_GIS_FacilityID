"""
Author: Jesse Nestler
Date Created: Tue Jun 19 13:04:49 2018
Purpose: Create a catalog of functions used for script automation
"""

"""
*******************************************************************************
IMPORT LIBRARIES
*******************************************************************************
"""
# standard libraries
import itertools
import openpyxl as pyxl
import pandas as pd
import datetime
import os
from os import path

# third party libraries
import arcpy
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEBase import MIMEBase
from email import Encoders

# local libraries
from boulder_gis import utilities as utils


def email(subject=None, email_body=None, recipients=None, attachments=None):
    """
    Used to send email notification (encoded in HTML) of success or failure of the process.
    
    :param subject (str): the subject header of the email
    :param email_body (str): the email body that will be encoded in HTML
    :param recipients (list or str): the recipients of the email
    :param attachments (list): the files to attach
    :return: {none} sends an email
    """
    # from/to addresses
    sender = 'noreply@bouldercolorado.gov'
    password = utils.forcode('noreply', '\xa1\xe0\xbb\xcf\xdb\xd4\xaa\x97\xe5\xc7', '')
    
    # message
    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = "; ".join(recipients) if isinstance(recipients, list) else recipients
    msg['Subject'] = subject
    
    # body
    body =  """\
            <html>
                <head></head>
                <body>
                    <p>
                    Dear Human,<br><br>
                    {}
                    </p>
                    <p>
                    Beep Boop Beep,<br><br>
                    End Transmision
                    </p>
                </body>
            </html>
            """.format(email_body)

    if attachments:
        files = [attachments] if not isinstance(attachments, list) else attachments
        for item in files:
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


def setup_log(root=None):
    """Creates a folder structure for logging script processes, and opens a log file object.

    :param root: the root path the user wishes to store the log file. If none, creates a folder in the working dir
    :return: file object of the log file
    """
    # create a logging directory in the root folder if none exists
    root = path.abspath(os.getcwd()) if not root else root
    log_path = path.join(root, 'Logs')
    if not (path.exists(log_path) and path.isdir(log_path)):
        os.makedirs(log_path)

    # name the log file and place it in the logging directory
    start = datetime.datetime.now()
    start_date = start.strftime("%Y%m%d")
    start_time = start.strftime('%H%M')
    log_name = path.join(log_path, 'LogFrom{}_{}.log'.format(start_date, start_time))

    # create file object
    log = open(log_name, 'w')
    return log


def log_time(l = None, line = None):
    """
    Creates a formatted line with the time. Use in the log.write() function.
    
    :param l (file object): The log being written through the open() function
    :param line (str): The message you want to write to your log file
    :return (str): A formatted string (H:M S -- {line})
    """
    time_stamp = datetime.datetime.now().strftime('%m/%d/%Y %H:%M:%S')
    content = "[{}] -- {}\n".format(time_stamp, line)
    print content
    return l.write(content)


def create_version_and_db_connection(save_path = None, v_name = None, 
                                     parent = None, workspace = None,
                                     conn_name = None):
    """
    Creates a version along with a database connection that enables scripting 
    edits.
    
    :param save_path: {str} The file path to save the temporary database connection.
    :param v_name (str): The name of the version to be created
    :param parent (str): The name of the parent version
    :param workspace (str): The workspace from which the version is created
    :conn_name (str): The name of the sde connection
    :return: {none} The function modifies arc verions and db connections
    """
    permiss = "PRIVATE"
    path_to_sde = path.join(save_path, '{}.sde'.format(conn_name))
    
    # Create version (if it already exists, delete and recreate)
    version = 'GISSCR.{}'.format(v_name)
    if any(version in v for v in arcpy.ListVersions(workspace)):
        arcpy.DeleteVersion_management(workspace, v_name)
        
    arcpy.CreateVersion_management(in_workspace = workspace,
                                   parent_version = parent,
                                   version_name = v_name,
                                   access_permission = permiss)
    
    # Create DB Connection from version
    if not path.isfile(path_to_sde) and not path.exists(path_to_sde):
        arcpy.CreateDatabaseConnection_management(out_folder_path = save_path,
                                                  out_name = conn_name,
                                                  database_platform = 'ORACLE',
                                                  instance = 'gisprod2', #
                                                  account_authentication = 'DATABASE_AUTH',
                                                  username = 'gisscr',
                                                  password = "gKJTZkCYS937",
                                                  version_type = 'TRANSACTIONAL',
                                                  version = version)


def find_privileges(sde = None, owner = None, table = None):
    """ Lists users by their view and edit permissions on a feature
    
    :param sde: path to the sde connection file 
    :param owner: the owner of the connection file (in UPPER case)
    :param table: the feature class or table in question (in UPPER case)
    :return: a dictionary of 'edit' and 'view' permissions
    :raise: TypeError if Oracle query does not have the correct inputs
    """
    global result
    privileges  = {"edit": set(), "view": set()}
    command = """
        select PRIVILEGE, GRANTEE
        from ALL_TAB_PRIVS 
        where TABLE_NAME = '{0}'
        and TABLE_SCHEMA = '{1}'""".format(table.upper(), owner.upper())
    executor = arcpy.ArcSDESQLExecute(sde)
    result = executor.execute(command)
    for row in result:
        if row[0] == "SELECT":
            privileges["view"].add(row[1])
        elif row[0] in ("UPDATE", "INSERT", "DELETE"):
            privileges["edit"].add(row[1])
    return privileges


def find_dirs(workspace = None, users = None):
    """
    This funtion finds all possible feature classes and datasets to examine 
    given a list of data owners. This function mostly helps in reducing how 
    many nested loops exist in the main block of code below by packaging lists 
    together.
    
    :param workspace (list): the top level root workspace (must be SDE)
    :param users (list): A list of data owners in PROD2 that must be examined
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


def excel_to_df(excel_file = None, headers = False, index = False):
    """ Converts the active worksheet inside an excel workbook into a df.
    
    :param excel_file: (str) file path to the excel file (w/ ".xlsx" extension)
    :param headers: (bool) indicates whether the spreadsheet has headers
    :param index: (bool) indicates whether the spreadsheet has an index column
    """
    # Read from Excel spreadsheet
    book = pyxl.load_workbook(excel_file)
    # List sheets in the workbook
    sheets = book.sheetnames
    # Iterate through sheets and extract the table data to a pandas df
    result = {}
    for sheet_name in sheets:
        # Activate the named worksheet
        book.active = book[sheet_name]
        # Create a worksheet object from the active sheet
        sheet = book.active
        # Create the data frame based on the presence of headers/indices
        if not index and not headers:
            # Convert to pandas with no headers or indices
            df = pd.DataFrame(sheet.values)
        else:
            # Convert to pandas with either/or/both headers and indices
            d = list(sheet.values)
            cols = None
            idx = None
            if headers:
                cols = d.pop(0)
            if index:
                idx = [r[0] for r in d]
            data = (itertools.islice(r, 0, None) for r in d)
            df = pd.DataFrame(data, columns=cols, index=idx)
        result[sheet_name] = df

    return result
