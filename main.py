import sys
import logging
from PyQt6 import QtWidgets, QtGui
import os
from pathlib import Path
from ui_nav import MainWindow

# --- Constants ---
APP_NAME = "SoilSight"
BASE_DIR = os.path.dirname(__file__)
LAYOUT_PATH = os.path.join(BASE_DIR, "mpcamera", "layouts", f"{APP_NAME}_MainWindow.ui")
ICON_PATH = os.path.join(BASE_DIR, "mpcamera", "assets", f"{APP_NAME}_Logo.ico")


def setup_logging():
    """Set up logging to file for debugging packaged app issues."""
    try:
        log_dir = Path.home() / ".mpcamera"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "debug.log"

        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        logging.info(f"Logging to {log_file}")
    except Exception as e:
        print(f"Failed to set up logging: {e}")


def setup_application_properties(app: QtWidgets.QApplication):
    """Sets application-wide properties like style and icon."""
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    app.setApplicationName(APP_NAME)

    try:
        app.setApplicationDisplayName(APP_NAME)
    except Exception:
        pass

    if os.path.exists(ICON_PATH):
        try:
            app.setWindowIcon(QtGui.QIcon(ICON_PATH))
        except Exception as e:
            print(f"Warning: Failed to set application icon. Error: {e}")


def main():
    setup_logging()
    logging.info(f"Starting {APP_NAME}")

    app = QtWidgets.QApplication(sys.argv)

    setup_application_properties(app)

    # Sync .env API URLs to config.json
    try:
        from mpcamera.config import sync_env_to_config
        sync_env_to_config()
    except Exception:
        pass

    win = MainWindow(LAYOUT_PATH)

    win.setWindowTitle(APP_NAME)

    if os.path.exists(ICON_PATH):
        try:
            win.setWindowIcon(QtGui.QIcon(ICON_PATH))
        except Exception:
            pass

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
