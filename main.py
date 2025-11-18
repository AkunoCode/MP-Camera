import sys
from PyQt6 import QtWidgets
from ui_nav import MainWindow
import os


def main():
    app = QtWidgets.QApplication(sys.argv)
    ui_path = os.path.join(
        os.path.dirname(__file__), "mpcamera", "layouts", "SoilSight_MainWindow.ui"
    )
    win = MainWindow(ui_path)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
