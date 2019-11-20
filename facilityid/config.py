import yaml
import logging
import getpass

import logging.config
import logging.handlers

username = getpass.getuser()
user_email = f"{username}@bouldercolorado.gov"

with open(r'.\facilityid\config.yaml') as config_file:
    config = yaml.safe_load(config_file)
    logging.config.dictConfig(config['LOGGING'])

# Which database?
db = config["platform"]
database = config["DATABASES"][db]

# Database connections
read = database["connections"]["read"]
edit = database["connections"]["edit"]

# Database properties
db_params = database["info"]

# Versioning configurations
post_edits = config["post_edits"]

# Data owners that authorize versioned edits
auth = [k for k, v in config["authorizes_edits"].items() if v]

# Filters for analysis
single_parent = config["single_parent"]

if single_parent:
    procedure = config["single"]
else:
    procedure = config["multiple"]
