import sys
from PyQt6 import QtWidgets
from ui_nav import MainWindow
import os


def main():
    app = QtWidgets.QApplication(sys.argv)
    # Use the Fusion style for a more consistent cross-platform look
    try:
        app.setStyle("Fusion")
    except Exception:
        pass
    ui_path = os.path.join(
        os.path.dirname(__file__), "mpcamera", "layouts", "SoilSight_MainWindow.ui"
    )
    win = MainWindow(ui_path)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
