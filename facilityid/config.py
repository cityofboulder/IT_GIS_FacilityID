import getpass
import logging
import logging.config
import logging.handlers

import yaml

username = getpass.getuser()
user_email = f"{username}@bouldercolorado.gov"

with open(r'.\facilityid\config.yaml') as config_file:
    config = yaml.safe_load(config_file.read())
    config['LOGGING']['handlers']['email']['toaddrs'] = user_email
    logging.config.dictConfig(config['LOGGING'])

# Pro project location
aprx = config["aprx"]
lyr = config["template_lyr"]

# Which database?
db = config["platform"]
database = config["DATABASES"][db]

# Database connections
read = database["connections"]["read"]
edit = database["connections"]["edit"]

# Database properties
db_params = database["info"]
db_creds = database["credentials"]

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
