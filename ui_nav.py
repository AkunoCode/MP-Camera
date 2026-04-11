from PyQt6 import uic, QtWidgets, QtGui, QtCore
from PyQt6.QtCore import pyqtSignal, QUrl
import os
import json
from threading import Thread

try:
    from mpcamera.services.directus import DirectusClient
except Exception:
    DirectusClient = None

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
    # Emitted on the main thread when Directus data has been fetched and cached
    dataLoaded = pyqtSignal()
    SELECTED_STYLE = "background-color: white;"
    UNSELECTED_STYLE = "background-color: black;"

    def __init__(self, ui_path: str):
        super().__init__()
        uic.loadUi(ui_path, self)

        # enforce a fixed window size per user request
        try:
            self.setFixedSize(1170, 760)
        except Exception:
            pass

        # ensure stacked widget shows homepage (index 0) by default
        try:
            sw = getattr(self, "stackedWidget", None)
            if sw is not None:
                try:
                    sw.setCurrentIndex(0)
                except Exception:
                    pass
        except Exception:
            pass

        # place soilsight_full.png into the center of the homepage (stackedWidget index 0)
        try:
            assets_path = os.path.join(
                os.path.dirname(__file__), "mpcamera", "assets", "soilsight_full.png"
            )
            if os.path.exists(assets_path):
                # try to locate the homepage widget by name or by stacked widget index
                page = None
                try:
                    page = self.findChild(QtWidgets.QWidget, "homePage")
                except Exception:
                    page = None

                if page is None and sw is not None:
                    try:
                        page = sw.widget(0)
                    except Exception:
                        page = None

                if page is not None:
                    label = QtWidgets.QLabel(page)
                    pix = QtGui.QPixmap(assets_path)
                    if not pix.isNull():
                        label.setPixmap(pix)
                    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                    # Put label into the page's layout, or create a centered one if absent
                    layout = page.layout()
                    if layout is None:
                        v = QtWidgets.QVBoxLayout()
                        v.setContentsMargins(0, 0, 0, 0)
                        v.addWidget(
                            label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter
                        )
                        page.setLayout(v)
                    else:
                        layout.addWidget(
                            label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter
                        )
        except Exception as e:
            print("Failed to place soilsight image on homepage:", e)

        # mapping from nav widget name -> stacked index
        # Note: stackedWidget indices are: home=0, farm=1, samples=2, camera=3, settings=4
        # chartNavButton is handled specially (opens external link) and should not map to the settings index.
        self.nav_map = {
            "soilsightLogo": 0,
            "farmNavButton": 1,
            "samplesNavButton": 2,
            "cameraNavButton": 3,
            "chartNavButton": None,
            "settingsNavButton": 4,
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

        # If a separate cameraPage.ui exists, load it into the placeholder page
        try:
            camera_ui_path = os.path.join(
                os.path.dirname(__file__), "mpcamera", "layouts", "cameraPage.ui"
            )
            camera_page = self.findChild(QtWidgets.QWidget, "cameraPage")
            if camera_page is not None and os.path.exists(camera_ui_path):
                print("Loading cameraPage UI from:", camera_ui_path)
                uic.loadUi(camera_ui_path, camera_page)
                # delegate camera initialization to the page module
                try:
                    from mpcamera.controllers import camera_page as camera_page_module

                    camera_page_module.setup(camera_page, self)
                except Exception as e:
                    print("Failed to initialize camera page module:", e)
            else:
                print(
                    "cameraPage placeholder not found or cameraPage.ui missing at:",
                    camera_ui_path,
                )
        except Exception as e:
            print("Error setting up cameraPage UI:", e)
        # If a separate farmPage.ui exists, load it into the placeholder page
        try:
            farm_ui_path = os.path.join(
                os.path.dirname(__file__), "mpcamera", "layouts", "farmPage.ui"
            )
            farm_page = self.findChild(QtWidgets.QWidget, "farmPage")
            if farm_page is not None and os.path.exists(farm_ui_path):
                print("Loading farmPage UI from:", farm_ui_path)
                try:
                    uic.loadUi(farm_ui_path, farm_page)
                except Exception as e:
                    print("Failed to load farmPage.ui into placeholder:", e)
                # if there is a farm page controller, call its setup(camera_page, self)
                try:
                    from mpcamera.controllers import farm_page as farm_page_module

                    try:
                        farm_page_module.setup(farm_page, self)
                    except Exception:
                        pass
                except Exception:
                    # no controller module present; that's fine
                    pass
            else:
                print(
                    "farmPage placeholder not found or farmPage.ui missing at:",
                    farm_ui_path,
                )
        except Exception as e:
            print("Error setting up farmPage UI:", e)
        # If a separate samplePage.ui exists, load it into the placeholder page
        try:
            sample_ui_path = os.path.join(
                os.path.dirname(__file__), "mpcamera", "layouts", "samplePage.ui"
            )
            samples_page = self.findChild(QtWidgets.QWidget, "samplesPage")
            if samples_page is not None and os.path.exists(sample_ui_path):
                print("Loading samplePage UI from:", sample_ui_path)
                try:
                    uic.loadUi(sample_ui_path, samples_page)
                except Exception as e:
                    print("Failed to load samplePage.ui into placeholder:", e)
                try:
                    from mpcamera.controllers import samples_page as samples_page_module

                    try:
                        samples_page_module.setup(samples_page, self)
                    except Exception:
                        pass
                except Exception:
                    pass
            else:
                print(
                    "samplesPage placeholder not found or samplePage.ui missing at:",
                    sample_ui_path,
                )
        except Exception as e:
            print("Error setting up samplesPage UI:", e)
        # If a separate chartPage.ui exists, load it into the placeholder page
        # chart page removed: we intentionally do not load chartPage.ui
        # If a separate settingsPage.ui exists, load it into the placeholder page
        try:
            settings_ui_path = os.path.join(
                os.path.dirname(__file__), "mpcamera", "layouts", "settingsPage.ui"
            )
            settings_page = self.findChild(QtWidgets.QWidget, "settingsPage")
            if settings_page is not None and os.path.exists(settings_ui_path):
                print("Loading settingsPage UI from:", settings_ui_path)
                try:
                    uic.loadUi(settings_ui_path, settings_page)
                except Exception as e:
                    print("Failed to load settingsPage.ui into placeholder:", e)
                try:
                    from mpcamera.controllers import (
                        settings_page as settings_page_module,
                    )

                    try:
                        settings_page_module.setup(settings_page, self)
                    except Exception:
                        pass
                except Exception:
                    pass
            else:
                print(
                    "settingsPage placeholder not found or settingsPage.ui missing at:",
                    settings_ui_path,
                )
        except Exception as e:
            print("Error setting up settingsPage UI:", e)
        # start fetching Directus data in background so pages can populate
        try:
            self._start_directus_fetch()
        except Exception as e:
            print("Failed to start Directus fetch:", e)

    def closeEvent(self, event):
        """Ensure camera and threads are cleaned up on window close."""
        try:
            if hasattr(self, "_camera_controller") and self._camera_controller is not None:
                self._camera_controller.cleanup()
        except Exception as e:
            print(f"Cleanup error on close: {e}")
        super().closeEvent(event)

    def _highlight_frame_for_nav(self, nav_name: str):
        frame_name = self.frame_map.get(nav_name)
        if not frame_name:
            return
        frame = self.findChild(QtWidgets.QFrame, frame_name)
        if frame is not None:
            frame.setStyleSheet(self.SELECTED_STYLE)

    def on_nav_clicked(self, nav_name: str):
        """Handle navigation clicks from the sidebar labels.

        - Switch the `stackedWidget` to the index mapped by `nav_name`.
        - Set all frames to UNSELECTED (black) then highlight the selected frame white.
        - Special-case `soilsightLogo`: go to index 0 and leave all frames unselected.
        """
        try:
            print(f"Nav clicked: {nav_name}")
            # special-case chartNavButton: ask user whether to open external link in browser
            if nav_name == "chartNavButton":
                try:
                    mb = QtWidgets.QMessageBox(self)
                    mb.setIcon(QtWidgets.QMessageBox.Icon.Question)
                    mb.setWindowTitle("Open in browser?")
                    mb.setText("Open SoilSight in your browser?")
                    mb.setInformativeText(
                        "This will open https://soilsight-one.vercel.app in your default web browser."
                    )
                    mb.setStandardButtons(
                        QtWidgets.QMessageBox.StandardButton.Yes
                        | QtWidgets.QMessageBox.StandardButton.No
                    )
                    resp = mb.exec()
                    if resp == QtWidgets.QMessageBox.StandardButton.Yes:
                        try:
                            import webbrowser

                            webbrowser.open("https://soilsight-one.vercel.app")
                        except Exception as e:
                            print("Failed to open browser:", e)
                except Exception as e:
                    print("Error prompting to open external chart link:", e)
                # do not change stacked widget index for chart navigation
                return

            # switch stacked widget index if present
            sw = getattr(self, "stackedWidget", None)
            if sw is not None:
                idx = self.nav_map.get(nav_name)
                if idx is not None:
                    try:
                        sw.setCurrentIndex(idx)
                    except Exception:
                        # some UIs use setCurrentWidget; try to be defensive
                        try:
                            sw.setCurrentIndex(int(idx))
                        except Exception:
                            pass
                    # If the Farm page was selected, refresh Directus data so pages stay up-to-date
                    try:
                        if nav_name == "farmNavButton":
                            try:
                                self._start_directus_fetch()
                            except Exception as e:
                                print("Failed to refresh Directus on nav change:", e)
                    except Exception:
                        pass

            # reset all frames to UNSELECTED
            for frame_name in [
                "farmFrame",
                "samplesFrame",
                "cameraFrame",
                "chartFrame",
                "settingsFrame",
                "logoFrame",
            ]:
                f = self.findChild(QtWidgets.QFrame, frame_name)
                if f is not None:
                    f.setStyleSheet(self.UNSELECTED_STYLE)

            # if soilsightLogo was clicked, do not highlight any frame (per spec)
            if nav_name == "soilsightLogo":
                return

            # otherwise highlight the associated frame
            try:
                self._highlight_frame_for_nav(nav_name)
            except Exception as e:
                print("Error highlighting frame for nav:", e)
        except Exception as e:
            print("Error in on_nav_clicked:", e)

    # Chart zoom helpers are handled by mpcamera.pages.chart_page; delegated there.

    # -- Directus fetching helpers -------------------------------------------------
    def _start_directus_fetch(self):
        """Start a background thread to fetch Directus `sites` and `soilsamples`.

        Results are stored on the window as `self.sites` and `self.soilsamples`.
        When complete the `dataLoaded` signal is emitted on the main thread.
        """
        if DirectusClient is None:
            print("DirectusClient not available (module import failed); skipping fetch")
            return

        def worker():
            try:
                client = DirectusClient()
                print("Directus: fetching sites...")
                sites = client.get_sites(params={"fields": "*"})
                print("Directus: fetching soilsamples...")
                soils = client.get_soilsamples(params={"fields": "*"})
                # store results on the main window
                self.sites = sites
                self.soilsamples = soils
                # Directus data fetched; not writing cache files to disk per configuration
                print("Directus data fetched (not cached to disk)")
                print("Directus fetch complete")
                # notify main thread
                try:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_on_directus_loaded",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                    )
                except Exception:
                    # fallback: emit signal directly
                    try:
                        self.dataLoaded.emit()
                    except Exception:
                        pass
            except Exception as e:
                print("Directus fetch failed:", e)

        t = Thread(target=worker, daemon=True)
        t.start()

    @QtCore.pyqtSlot()
    def _on_directus_loaded(self):
        """Called on the main thread after Directus data has been fetched."""
        try:
            self.dataLoaded.emit()
        except Exception:
            pass

    def get_sites(self):
        """Return cached sites data or None if not yet fetched."""
        return getattr(self, "sites", None)

    def get_soilsamples(self):
        """Return cached soilsamples data or None if not yet fetched."""
        return getattr(self, "soilsamples", None)

    def _extract_directus_items(self, obj):
        """Helper to extract list of items from a Directus response.

        Directus responses often come as {'data': [...]} or directly as a list.
        """
        if obj is None:
            return []
        try:
            if isinstance(obj, dict) and "data" in obj:
                return obj.get("data") or []
            if isinstance(obj, list):
                return obj
        except Exception:
            pass
        return []

    # Camera page population/wiring is handled by mpcamera.pages.camera_page.setup

    # Soil combo population delegated to camera_page

    # site id extraction handled in camera_page

    # farm change handled in camera_page

    # soil change handled in camera_page
