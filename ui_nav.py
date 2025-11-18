from PyQt6 import uic, QtWidgets, QtGui, QtCore
from PyQt6.QtCore import pyqtSignal


class ClickableLabel(QtWidgets.QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    SELECTED_STYLE = "background-color: white;"
    UNSELECTED_STYLE = "background-color: black;"

    def __init__(self, ui_path: str):
        super().__init__()
        uic.loadUi(ui_path, self)

        # mapping from nav widget name -> stacked index
        self.nav_map = {
            "soilsightLogo": 0,
            "farmNavButton": 1,
            "samplesNavButton": 2,
            "cameraNavButton": 3,
            "chartNavButton": 4,
            "settingsNavButton": 5,
        }

        # mapping from nav widget -> its parent frame name
        self.frame_map = {
            "farmNavButton": "farmFrame",
            "samplesNavButton": "samplesFrame",
            "cameraNavButton": "cameraFrame",
            "chartNavButton": "chartFrame",
            "settingsNavButton": "settingsFrame",
        }

        # replace the QLabel instances with ClickableLabel behavior by connecting mousePressEvent
        for name in self.nav_map.keys():
            widget = self.findChild(QtWidgets.QLabel, name)
            if widget is None:
                continue

            # If the widget is already our ClickableLabel subclass (unlikely when loaded from .ui), connect directly
            if isinstance(widget, ClickableLabel):
                widget.clicked.connect(lambda n=name: self.on_nav_clicked(n))
            else:
                # Monkey-patch mousePressEvent to call our handler
                def make_handler(n):
                    def handler(event):
                        self.on_nav_clicked(n)

                    return handler

                widget.mousePressEvent = make_handler(name)
            # make it look like a clickable button
            try:
                widget.setCursor(
                    QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor)
                )
            except Exception:
                pass

        # ensure frames exist and set initial styles (all unselected / black)
        for frame_name in [
            "farmFrame",
            "samplesFrame",
            "cameraFrame",
            "chartFrame",
            "settingsFrame",
            "logoFrame",
        ]:
            frame = self.findChild(QtWidgets.QFrame, frame_name)
            if frame is not None:
                frame.setStyleSheet(self.UNSELECTED_STYLE)
                # give frames a pointing-hand cursor so the whole area feels clickable
                try:
                    frame.setCursor(
                        QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor)
                    )
                except Exception:
                    pass

        # load initial index (UI may have a default) but make frames consistent
        current = getattr(self, "stackedWidget", None)
        if current is not None:
            # if the UI default index corresponds to a nav frame, highlight it
            idx = current.currentIndex()
            # try to find matching nav by index
            for k, v in self.nav_map.items():
                if v == idx and k != "soilsightLogo":
                    self._highlight_frame_for_nav(k)
                    break

    def on_nav_clicked(self, name: str):
        # soilsightLogo behaves as home: set stacked index 0 and make all frames black
        if name == "soilsightLogo":
            if hasattr(self, "stackedWidget"):
                self.stackedWidget.setCurrentIndex(0)
            # set all frames to unselected
            self._clear_all_frames()
            return

        # set stacked index
        idx = self.nav_map.get(name)
        if idx is not None and hasattr(self, "stackedWidget"):
            self.stackedWidget.setCurrentIndex(idx)

        # update frame highlights
        self._clear_all_frames()
        self._highlight_frame_for_nav(name)

    def _clear_all_frames(self):
        for frame_name in [
            "farmFrame",
            "samplesFrame",
            "cameraFrame",
            "chartFrame",
            "settingsFrame",
            "logoFrame",
        ]:
            frame = self.findChild(QtWidgets.QFrame, frame_name)
            if frame is not None:
                frame.setStyleSheet(self.UNSELECTED_STYLE)

    def _highlight_frame_for_nav(self, nav_name: str):
        frame_name = self.frame_map.get(nav_name)
        if not frame_name:
            return
        frame = self.findChild(QtWidgets.QFrame, frame_name)
        if frame is not None:
            frame.setStyleSheet(self.SELECTED_STYLE)
