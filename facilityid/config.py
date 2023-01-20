import logging
import logging.config
import logging.handlers
import os
from cryptography.fernet import Fernet

import yaml


def decrypt(key, token):
    """This function decrypts encrypted text back into plain text.

    Parameters:
    -----------
    key : str
        Encryption key
    token : str
        Encrypted text

    Returns:
    --------
    str
        Decrypted plain text
    """

    decrypted = ""
    try:
        f = Fernet(key)
        decrypted = f.decrypt(bytes(token, 'utf-8'))
    except Exception:
        pass

    return decrypted.decode("utf-8")

# Get credentials
with open(r'.\facilityid\credentials.yaml') as cred_file:
    creds = yaml.safe_load(cred_file.read())
    no_reply = creds['EMAIL']['address']
    no_reply_password = decrypt(
        creds['EMAIL']['credentials']['key'],
        creds['EMAIL']['credentials']['token']
    )

# Get configurations
with open(r'.\facilityid\config.yaml') as config_file:
    config = yaml.safe_load(config_file.read())
    config['LOGGING']['handlers']['email']['credentials'] = [
        no_reply,
        no_reply_password
    ]
    logging.config.dictConfig(config['LOGGING'])

# Pro project location
aprx = config["aprx"]
lyr = config["template_lyr"]

# Recycle IDs?
recycle = config["recycle_ids"]

# Which database?
db = config["platform"]
database = config["DATABASES"][db]

# Database properties
db_params = database["info"]
db_key = creds['DATABASES'][db]['key']
db_token = creds['DATABASES'][db]['token']
db_password = decrypt(db_key, db_token)

# Database connections
read = os.path.realpath(database["connections"]["read"])
edit = os.path.realpath(database["connections"]["edit"])

# Data owners that authorize versioned edits
versioned_edits = [
    k for k, v in config["authorization"].items() if v["versioned_edits"]]

# Data owners that authorize posting edits
post_edits = [k for k, v in config["authorization"].items()
              if v["post_edits"]]

# Filters for analysis
single_parent = config["single_parent"]

if single_parent:
    procedure = config["single"]
else:
    procedure = config["multiple"]

recipients = config['recipients']
