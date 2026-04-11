import sys
from PyQt6 import QtWidgets, QtGui
import os
from ui_nav import MainWindow
from mpcamera.logging_utils import setup_logging, get_logger
from mpcamera.path_utils import get_resource_path

logger = get_logger(__name__)

# --- Constants ---
APP_NAME = "SoilSight"
LAYOUT_PATH = get_resource_path(f"mpcamera/layouts/{APP_NAME}_MainWindow.ui")
ICON_PATH = get_resource_path(f"mpcamera/assets/{APP_NAME}_Logo.ico")


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
    logger.info(f"Starting {APP_NAME}")

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
