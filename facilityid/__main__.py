from facilityid import app
import logging

logging.basicConfig(filename='app.log',
                    level=logging.INFO,
                    format='%(asctime)s : %(levelname)s : %(message)s',
                    datefmt='%d-%b-%y %H:%M:%S')


if __name__ == "__main__":
    try:
        app.main()
    except Exception:
        logging.critical("Something prevented the app from running")
