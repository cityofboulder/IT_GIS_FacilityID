import os

import app
import config

# Initiate a logger for __main__
log = config.logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        app.main()
    except Exception:
        log.exception("Something prevented the script from running")
    finally:
        conn_files = [os.path.join(root, f) for root, _, f in os.walk(
            os.getcwd()) if f.endswith(".sde")]
        if conn_files:
            for connection in conn_files:
                os.remove(connection)
