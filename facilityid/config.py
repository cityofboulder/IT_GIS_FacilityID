import yaml

with open(r'.\facilityid\config.yaml') as config_file:
    config = yaml.safe_load(config_file)

# Versioning configurations
post_edits = config["post_edits"]

# Data owners that authorize versioned edits
auth = [k for k, v in config["authorizes_edits"].items() if v]

# Database connections
read = config["connections"]["read"]
edit = config["connections"]["edit"]

# Filters for analysis
single_parent = config["single_parent"]

if single_parent:
    procedure = config["single"]
else:
    procedure = config["multiple"]
