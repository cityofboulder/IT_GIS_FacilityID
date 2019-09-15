## Versioned Edits to Unique IDs

Th main app within this package QCs unique, human-readable IDs in a versioned database. It specifically looks for duplicated and null IDs, as well as erroneous prefixes and other useful tweaks. It also leverages the power of enterprise versioning to make edits, so that DEFAULT remains intact until a human can verify edits before committing.

### Installation and Use
---

#### Assumptions

This package makes use of the `arcpy` library and Python 3. It also produces Excel spreadsheets detailing the errors found, and it delivers those spreadsheets over email to a defined user-group. As such, this package leverages the base conda environment that ships with ArcGIS Pro, as many of necessary libraries come pre-installed.

#### Set Up

Clone this repo to your preffered location using Git (or download through the [repo website](https://github.com/jessenestler/facilityid)):

```
cd your/preferred/project/location
git clone "https://github.com/jessenestler/facilityid"
```

Now, clone the base `arcgispro-py3` environment by [following these instructions](https://pro.arcgis.com/en/pro-app/arcpy/get-started/what-is-conda.htm), or running a quick command through the Command Prompt:

```
conda create --name facilityid_env --clone arcgispro-py3
```

#### Running the Script

In the Command Prompt, change directories to the parent folder of the facilityid download:

```
cd /d parent\of\wherever\you\just\downloaded\this\package
```

Now, still in Command Prompt, enter into the conda environment created especially for this package:

```
conda activate facilityid_env
```

Lastly, tell Python to do its thing!

```
python -m facilityid
```