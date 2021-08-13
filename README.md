# Versioned Edits to Unique IDs

This package QCs unique, human-readable IDs in an enterprise geodatabase. It specifically looks for duplicated and null IDs, as well as erroneous prefixes and other useful tweaks. It also leverages the power of database versioning to make edits, so that records inside DEFAULT remains intact until a human can verify edits before committing them.

## Installation
---

### Assumptions

This package makes use of the `arcpy` library and Python 3; as such, it leverages the base conda environment that ships with ArcGIS Pro. Conda is a python package manager. A one-time setup of a conda python instance should be done under the following circumstances:

- When the script is run on a new computer
- When ArcGIS Pro is upgraded on whichever computer is running the script.

### Set Up Conda

1. Make sure that your computer knows where the ArcGIS Pro Conda executable lives by adding this path to your computer's *system* Path environment variable: `C:\Program Files\ArcGIS\Pro\bin\Python\Scripts`
2. Run the batch script called `setup_conda_env.bat`.

### Saving a Pro Project

*If you decide to post edits automatically, or if there is already a Pro project downloaded, you can forgo this step entirely.*

Part of the output of this tool is a series of layer files that get emailed to a specifc user group. In order to create those layer files, you'll first need to create a Pro project with a couple of maps inside. This only needs to be done once, before running the script for the first time.

1. Create a new Pro project and save it in the `.\.esri\` folder shipped with this package. Call the project whatever you want, and **make sure to unselect the Create New Folder button**.
2. Open the project, and add a map for each user that will be scanned. For example, if UTIL, TRANS, and PW will be scanned, create a seperate map for each of those users, called UTIL, TRANS, and PW, respectively.
3. Create an empty group layer and save it as a `*.lyrx` file in the `.\.esri\` folder. Call it whatever you like.
4. Save the Pro project and close.
5. In `config.yaml`, write down the file path to the Pro project and Group template layer, either as absolute or relative paths.

### Configuring the Script

*You can forego this step if you are ok with the  default configuration.*

A number of configurations can be set before running the script. The full gamut of configurable variables can be found by navigating to the `config.yaml` file. Some of the more important knobs to twist are:

1. Posting edits automatically
2. Filtering which layers get analyzed
3. Specifying parent version(s) to post edits to
4. Specifying where the template aprx file is stored (irrelavent for when automatic posting is enabled)
5. Denoting which database to run a scan on
6. Listing users to send a final email

At a bare minimum, the script needs to know:

- `platform`: which database to run the scan on
- `authorizes_edits`: which users have authorized versioned edits
- `single_parent`: whether to follow a single- or multiple-parent architecture (if multiple-parents, make sure to specify a parent along with which layers and/or datasets to edit from that parent. See examples that are shipped with the default config file.)

## Running the Script
---

Simply navigate to wherever you saved the repo, and double click on the `run_script.bat` file. **Important note: the script will not run properly if you double-click any of the python files.**