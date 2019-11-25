import facilityid.app as app
import facilityid.config as config
from facilityid.utils.management import remove_files

# Initiate a logger for __main__
log = config.logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        app.main()
    except Exception:
        log.exception("Something prevented the script from running")
    finally:
        remove_files(['.sde'])
