from PyQt6 import uic, QtWidgets, QtGui, QtCore
from PyQt6.QtCore import pyqtSignal, QUrl
import os
import json
from threading import Thread
try:
    from mpcamera.directus.directus import DirectusClient
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

        # Start background fetch of Directus collections (sites, soilsamples)
        try:
            self.sites = None
            self.soilsamples = None
            self._start_directus_fetch()
        except Exception as e:
            print("Failed to start Directus fetch:", e)

        # If a separate cameraPage.ui exists, load it into the placeholder page
        try:
            camera_ui_path = os.path.join(
                os.path.dirname(__file__), "mpcamera", "layouts", "cameraPage.ui"
            )
            camera_page = self.findChild(QtWidgets.QWidget, "cameraPage")
            if camera_page is not None and os.path.exists(camera_ui_path):
                print("Loading cameraPage UI from:", camera_ui_path)
                # load the camera page UI into the placeholder widget
                uic.loadUi(camera_ui_path, camera_page)

                # Basic diagnostics: list children created under cameraPage
                try:
                    children = camera_page.children()
                    names = [getattr(c, 'objectName', lambda: '')() if hasattr(c, 'objectName') else type(c).__name__ for c in children]
                    print("cameraPage children:", names)
                except Exception:
                    pass
                # attempt to populate farmCombo and soilCombo if data is available
                try:
                    if self.get_sites() is not None and self.get_soilsamples() is not None:
                        self._populate_camera_combos(camera_page)
                    else:
                        # populate when directus data arrives
                        try:
                            self.dataLoaded.connect(lambda: self._populate_camera_combos(camera_page))
                        except Exception:
                            pass
                except Exception as e:
                    print("Error scheduling cameraPage combo population:", e)
            else:
                print("cameraPage placeholder not found or cameraPage.ui missing at:", camera_ui_path)
        except Exception as e:
            print("Error setting up cameraPage UI:", e)

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
                    QtCore.QMetaObject.invokeMethod(self, "_on_directus_loaded", QtCore.Qt.ConnectionType.QueuedConnection)
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

    def _on_directus_loaded(self):
        """Called on the main thread after Directus data has been fetched."""
        try:
            self.dataLoaded.emit()
        except Exception:
            pass

    def get_sites(self):
        """Return cached sites data or None if not yet fetched."""
        return getattr(self, 'sites', None)

    def get_soilsamples(self):
        """Return cached soilsamples data or None if not yet fetched."""
        return getattr(self, 'soilsamples', None)

    def _extract_directus_items(self, obj):
        """Helper to extract list of items from a Directus response.

        Directus responses often come as {'data': [...]} or directly as a list.
        """
        if obj is None:
            return []
        try:
            if isinstance(obj, dict) and 'data' in obj:
                return obj.get('data') or []
            if isinstance(obj, list):
                return obj
        except Exception:
            pass
        return []

    def _populate_camera_combos(self, camera_page: QtWidgets.QWidget):
        """Populate `farmCombo` and `soilCombo` widgets inside `camera_page`.

        - `farmCombo` displays farm name (uses id as userData)
        - `soilCombo` displays: "Sample ID [id] (date_collected)" (uses id as userData)
        """
        try:
            farm_combo = camera_page.findChild(QtWidgets.QComboBox, 'farmCombo')
            soil_combo = camera_page.findChild(QtWidgets.QComboBox, 'soilCombo')
            sites = self._extract_directus_items(self.get_sites())
            soils = self._extract_directus_items(self.get_soilsamples())

            # store raw lists for later filtering
            self._camera_sites_list = sites
            self._camera_soils_list = soils

            # populate farms (add an explicit empty selection at index 0)
            if farm_combo is not None:
                try:
                    farm_combo.blockSignals(True)
                    farm_combo.clear()
                    for item in sites:
                        name = item.get('site_name') or item.get('name') or item.get('title') or str(item.get('id'))
                        farm_combo.addItem(str(name), item.get('id'))
                    # leave no selection at startup
                    try:
                        farm_combo.setCurrentIndex(-1)
                    except Exception:
                        pass
                    farm_combo.blockSignals(False)
                    print(f"Populated farmCombo with {len(sites)} entries")
                except Exception as e:
                    print("Failed to populate farmCombo:", e)

            # populate soilsamples (show all initially)
            if soil_combo is not None:
                try:
                    self._populate_soil_combo(camera_page, None)
                    # ensure no selection at startup
                    try:
                        soil_combo.setCurrentIndex(-1)
                    except Exception:
                        pass
                except Exception as e:
                    print("Failed to populate soilCombo:", e)

            # connect signals: selecting farm filters soils; selecting soil sets farm
            try:
                if farm_combo is not None and soil_combo is not None:
                    farm_combo.currentIndexChanged.connect(lambda idx, fc=farm_combo, cp=camera_page: self._on_farm_changed(fc, cp))
                    soil_combo.currentIndexChanged.connect(lambda idx, sc=soil_combo, fc=farm_combo: self._on_soil_changed(sc, fc))
            except Exception as e:
                print("Failed to connect camera combo signals:", e)
        except Exception as e:
            print("Error populating camera combos:", e)

    def _populate_soil_combo(self, camera_page: QtWidgets.QWidget, site_id):
        """Populate the `soilCombo` with soilsamples filtered by `site_id`.

        If `site_id` is None the method will show all soilsamples.
        """
        try:
            soil_combo = camera_page.findChild(QtWidgets.QComboBox, 'soilCombo')
            soils = getattr(self, '_camera_soils_list', []) or []
            if soil_combo is None:
                return
            soil_combo.blockSignals(True)
            soil_combo.clear()
            count = 0
            for item in soils:
                s_site = self._get_site_id_from_sample(item)
                if site_id is None or site_id == s_site:
                    sid = item.get('id')
                    date = item.get('date_collected') or item.get('date') or ''
                    label = f"Sample ID {sid} ({date})"
                    soil_combo.addItem(label, sid)
                    count += 1
            soil_combo.blockSignals(False)
            print(f"Populated soilCombo with {count} entries (filter site_id={site_id})")
        except Exception as e:
            print("Error in _populate_soil_combo:", e)

    def _get_site_id_from_sample(self, sample_item):
        """Return the site id for a soilsample item (handles scalar or nested site).

        Directus may return `site` as a scalar id or as an object; handle both.
        """
        if sample_item is None:
            return None
        try:
            site = sample_item.get('site')
            if isinstance(site, dict):
                return site.get('id')
            return site
        except Exception:
            return None

    def _on_farm_changed(self, farm_combo: QtWidgets.QComboBox, camera_page: QtWidgets.QWidget):
        try:
            data = farm_combo.currentData()
            site_id = data if data else None
            # repopulate soils according to selection (None shows all)
            self._populate_soil_combo(camera_page, site_id)
        except Exception as e:
            print("Error handling farm change:", e)

    def _on_soil_changed(self, soil_combo: QtWidgets.QComboBox, farm_combo: QtWidgets.QComboBox):
        try:
            data = soil_combo.currentData()
            if not data:
                return
            sid = data
            soils = getattr(self, '_camera_soils_list', []) or []
            match = None
            for item in soils:
                if item.get('id') == sid:
                    match = item
                    break
            if match is None:
                return
            site_id = self._get_site_id_from_sample(match)
            if site_id is None:
                return
            # set farm_combo to the matching site id if present
            try:
                idx = farm_combo.findData(site_id)
                if idx != -1:
                    farm_combo.setCurrentIndex(idx)
            except Exception:
                pass
        except Exception as e:
            print("Error handling soil change:", e)

