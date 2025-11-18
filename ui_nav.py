from PyQt6 import uic, QtWidgets, QtGui, QtCore
from PyQt6.QtCore import pyqtSignal, QUrl
import os

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:
    QWebEngineView = None


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

        # If a separate chartPage.ui exists, load it into the placeholder page
        try:
            chart_ui_path = os.path.join(
                os.path.dirname(__file__), "mpcamera", "layouts", "chartPage.ui"
            )
            chart_page = self.findChild(QtWidgets.QWidget, "chartPage")
            if chart_page is not None and os.path.exists(chart_ui_path):
                print("Loading chartPage UI from:", chart_ui_path)
                # load the chart page UI into the placeholder widget
                uic.loadUi(chart_ui_path, chart_page)

                # Try to find the promoted QWebEngineView by object name 'widget'
                webview = None
                if QWebEngineView is not None:
                    webview = chart_page.findChild(QWebEngineView, "widget")
                    if webview is None:
                        # try any QWebEngineView child
                        children = chart_page.findChildren(QWebEngineView)
                        webview = children[0] if children else None
                else:
                    # fallback: try to find any widget named 'widget'
                    webview = chart_page.findChild(QtWidgets.QWidget, "widget")

                # If not found, but QWebEngineView is available, create one and attach it
                if webview is None and QWebEngineView is not None:
                    try:
                        print("Promoted webview not found; creating QWebEngineView programmatically")
                        webview = QWebEngineView(chart_page)
                        webview.setObjectName("widget")
                        # position it to cover the chart page (use geometry from ui or full)
                        try:
                            webview.setGeometry(0, 0, chart_page.width() or 1100, chart_page.height() or 760)
                        except Exception:
                            webview.setGeometry(0, 0, 1100, 760)
                        webview.setParent(chart_page)
                        webview.show()
                    except Exception as e:
                        print("Failed to create QWebEngineView:", e)

                if webview is not None:
                    # keep a reference so other methods (zoom/reset) can access it
                    self.chart_webview = webview
                    try:
                        url = QUrl("https://soilsight-one.vercel.app")
                        # QWebEngineView supports setUrl or load
                        if hasattr(webview, "setUrl"):
                            webview.setUrl(url)
                        elif hasattr(webview, "load"):
                            webview.load(url)
                        print("Chart page webview instructed to load URL:", url.toString())
                    except Exception as e:
                        print("Failed to load URL into webview:", e)
                    # set default zoom factor to 1.0 (100%) if supported
                    try:
                        if hasattr(webview, 'setZoomFactor'):
                            webview.setZoomFactor(0.7)
                        elif hasattr(webview, 'page') and hasattr(webview.page(), 'setZoomFactor'):
                            webview.page().setZoomFactor(0.7)
                    except Exception:
                        pass

                    # Add keyboard shortcuts for zoom in/out/reset
                    try:
                        zoom_in_seq = QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.ZoomIn)
                        zoom_out_seq = QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.ZoomOut)
                        reset_seq = QtGui.QKeySequence("Ctrl+0")

                        zoom_in_sc = QtWidgets.QShortcut(zoom_in_seq, self)
                        zoom_in_sc.activated.connect(lambda: self._change_chart_zoom(0.1))

                        zoom_out_sc = QtWidgets.QShortcut(zoom_out_seq, self)
                        zoom_out_sc.activated.connect(lambda: self._change_chart_zoom(-0.1))

                        reset_sc = QtWidgets.QShortcut(reset_seq, self)
                        reset_sc.activated.connect(lambda: self._set_chart_zoom(1.0))
                    except Exception as e:
                        print("Failed to create zoom shortcuts:", e)
                else:
                    print("No webview available for chartPage (PyQt6 WebEngine not installed?)")
        except Exception as e:
            # don't crash if webengine isn't available or ui isn't present
            print("Error setting up chartPage webview:", e)

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

    def _set_chart_zoom(self, factor: float):
        """Set chart webview zoom factor to `factor` (e.g. 1.0 for 100%)."""
        webview = getattr(self, 'chart_webview', None)
        if webview is None:
            print("_set_chart_zoom: no chart_webview available")
            return
        try:
            if hasattr(webview, 'setZoomFactor'):
                webview.setZoomFactor(factor)
                print(f"Chart zoom set to {factor}")
                return
            if hasattr(webview, 'page') and hasattr(webview.page(), 'setZoomFactor'):
                webview.page().setZoomFactor(factor)
                print(f"Chart page zoom set to {factor}")
                return
            # fallback: use JS to change CSS zoom
            if hasattr(webview, 'runJavaScript'):
                try:
                    js = f"document.body.style.zoom = '{int(factor*100)}%';"
                    webview.runJavaScript(js)
                    print(f"Chart JS zoom set to {factor}")
                except Exception as e:
                    print("Failed to set zoom via JS:", e)
        except Exception as e:
            print("Error setting chart zoom:", e)

    def _change_chart_zoom(self, delta: float):
        """Increase or decrease zoom by `delta` (e.g. 0.1 to increase by 10%)."""
        webview = getattr(self, 'chart_webview', None)
        if webview is None:
            print("_change_chart_zoom: no chart_webview available")
            return
        try:
            current = None
            if hasattr(webview, 'zoomFactor'):
                current = webview.zoomFactor()
            elif hasattr(webview, 'page') and hasattr(webview.page(), 'zoomFactor'):
                current = webview.page().zoomFactor()
            if current is None:
                # can't read zoom; just set a reasonable default
                current = 1.0
            new = max(0.1, current + delta)
            self._set_chart_zoom(new)
        except Exception as e:
            print("Error changing chart zoom:", e)
