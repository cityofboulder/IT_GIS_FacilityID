import getpass
import logging

from facilityid import app

# Configure logging
logging.basicConfig(filename='FacilityID.log',
                    level=logging.INFO,
                    format='%(asctime)s : %(levelname)s : %(message)s',
                    datefmt='%d-%b-%y %H:%M:%S')

# User who initiated the script
username = getpass.getuser()

if __name__ == "__main__":
    try:
        app.main()
    except Exception:
        logging.critical("Something prevented the app from running")
