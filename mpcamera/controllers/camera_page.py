from PyQt6 import QtWidgets, QtCore, QtGui
from threading import Thread
import traceback
try:
    from mpcamera.services.roboflow import RoboflowClient
except Exception:
    RoboflowClient = None


def _extract_directus_items(obj):
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


def _get_site_id_from_sample(sample_item):
    if sample_item is None:
        return None
    try:
        site = sample_item.get("site")
        if isinstance(site, dict):
            return site.get("id")
        return site
    except Exception:
        return None


def setup(camera_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    """Set up `camera_page` UI using Directus data available on `main_window`.

    This populates `farmCombo` and `soilCombo` and wires their interactions.
    """
    try:
        farm_combo = camera_page.findChild(QtWidgets.QComboBox, "farmCombo")
        soil_combo = camera_page.findChild(QtWidgets.QComboBox, "soilCombo")

        def populate_from_cache():
            sites = _extract_directus_items(main_window.get_sites())
            soils = _extract_directus_items(main_window.get_soilsamples())

            # store raw lists on the main window for other modules that may want them
            setattr(main_window, "_camera_sites_list", sites)
            setattr(main_window, "_camera_soils_list", soils)

            # populate farms
            if farm_combo is not None:
                try:
                    farm_combo.blockSignals(True)
                    farm_combo.clear()
                    for item in sites:
                        name = item.get("site_name") or item.get("name") or item.get("title") or str(item.get("id"))
                        farm_combo.addItem(str(name), item.get("id"))
                    try:
                        farm_combo.setCurrentIndex(-1)
                    except Exception:
                        pass
                    farm_combo.blockSignals(False)
                    print(f"Populated farmCombo with {len(sites)} entries")
                except Exception as e:
                    print("camera_page: Failed to populate farmCombo:", e)

            # populate soils (initially all)
            if soil_combo is not None:
                try:
                    _populate_soil_combo(site_id=None)
                    try:
                        soil_combo.setCurrentIndex(-1)
                    except Exception:
                        pass
                except Exception as e:
                    print("camera_page: Failed to populate soilCombo:", e)

        def _populate_soil_combo(site_id=None):
            soils = getattr(main_window, "_camera_soils_list", []) or []
            if soil_combo is None:
                return
            soil_combo.blockSignals(True)
            soil_combo.clear()
            count = 0
            for item in soils:
                s_site = _get_site_id_from_sample(item)
                if site_id is None or site_id == s_site:
                    sid = item.get("id")
                    date = item.get("date_collected") or item.get("date") or ""
                    label = f"Sample ID {sid} ({date})"
                    soil_combo.addItem(label, sid)
                    count += 1
            soil_combo.blockSignals(False)
            print(f"Populated soilCombo with {count} entries (filter site_id={site_id})")

        def on_farm_changed():
            try:
                site_id = farm_combo.currentData()
                site_id = site_id if site_id else None
                _populate_soil_combo(site_id)
            except Exception as e:
                print("camera_page: Error handling farm change:", e)

        def on_soil_changed():
            try:
                sid = soil_combo.currentData()
                if not sid:
                    return
                soils = getattr(main_window, "_camera_soils_list", []) or []
                match = None
                for item in soils:
                    if item.get("id") == sid:
                        match = item
                        break
                if match is None:
                    return
                site_id = _get_site_id_from_sample(match)
                if site_id is None:
                    return
                # set farm selection to corresponding site if present
                try:
                    idx = farm_combo.findData(site_id)
                    if idx != -1:
                        farm_combo.setCurrentIndex(idx)
                except Exception:
                    pass
            except Exception as e:
                print("camera_page: Error handling soil change:", e)

        # If data already present, populate immediately, otherwise wait for main signal
        try:
            if main_window.get_sites() is not None and main_window.get_soilsamples() is not None:
                populate_from_cache()
            else:
                try:
                    main_window.dataLoaded.connect(populate_from_cache)
                except Exception:
                    pass
        except Exception as e:
            print("camera_page: scheduling population failed:", e)

        # wire signals
        try:
            if farm_combo is not None:
                farm_combo.currentIndexChanged.connect(lambda _: on_farm_changed())
            if soil_combo is not None:
                soil_combo.currentIndexChanged.connect(lambda _: on_soil_changed())
        except Exception as e:
            print("camera_page: failed to connect combo signals:", e)

        # Image upload -> show in QGraphicsView named 'cameraView'
        try:
            img_btn = camera_page.findChild(QtWidgets.QPushButton, "imgUploadButton")
            cam_view = camera_page.findChild(QtWidgets.QGraphicsView, "cameraView")

            # Create a simple overlay widget that will be shown on top of the camera view
            overlay = None
            class _Spinner(QtWidgets.QWidget):
                def __init__(self, parent=None, diameter=40, line_width=4, color=QtGui.QColor(255,255,255)):
                    super().__init__(parent)
                    self._angle = 0
                    self._timer = QtCore.QTimer(self)
                    self._timer.setInterval(16)
                    self._timer.timeout.connect(self._on_tick)
                    self._diameter = diameter
                    self._line_width = line_width
                    self._color = color
                    self.setFixedSize(diameter, diameter)

                def _on_tick(self):
                    self._angle = (self._angle + 8) % 360
                    self.update()

                def start(self):
                    if not self._timer.isActive():
                        self._timer.start()

                def stop(self):
                    try:
                        if self._timer.isActive():
                            self._timer.stop()
                    except Exception:
                        pass

                def paintEvent(self, ev):
                    r = self.rect()
                    painter = QtGui.QPainter(self)
                    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                    pen = QtGui.QPen(self._color)
                    pen.setWidth(self._line_width)
                    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                    painter.setPen(pen)
                    # draw arc
                    rect = QtCore.QRectF(self._line_width/2, self._line_width/2, r.width()-self._line_width, r.height()-self._line_width)
                    start_angle = int(self._angle * 16)
                    span = int(270 * 16)  # 270 degrees arc
                    painter.drawArc(rect, start_angle, span)
            class _ViewportEventFilter(QtCore.QObject):
                def __init__(self, overlay_widget):
                    super().__init__()
                    self._overlay = overlay_widget

                def eventFilter(self, obj, event):
                    try:
                        if event.type() == QtCore.QEvent.Type.Resize and self._overlay is not None:
                            self._overlay.setGeometry(obj.rect())
                    except Exception:
                        pass
                    return super().eventFilter(obj, event)

            def _ensure_overlay():
                nonlocal overlay
                try:
                    if cam_view is None:
                        return None
                    vp = cam_view.viewport()
                    if overlay is None:
                        overlay = QtWidgets.QWidget(vp)
                        overlay.setObjectName("camera_loading_overlay")
                        overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
                        overlay.setStyleSheet("#camera_loading_overlay { background: rgba(0,0,0,0.5); }")
                        lay = QtWidgets.QVBoxLayout(overlay)
                        lay.setContentsMargins(0, 0, 0, 0)
                        lay.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                        # place spinner directly on the overlay (no inner rounded rectangle)
                        v = lay
                        v.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                        spinner = _Spinner(overlay, diameter=36, line_width=4)
                        v.addWidget(spinner, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
                        # store spinner reference on the overlay so it persists
                        overlay._spinner = spinner
                        overlay.setGeometry(vp.rect())
                        # attach spinner and timer placeholders to overlay to avoid GC
                        overlay._spinner = spinner
                        overlay.hide()
                        # install resize filter so overlay follows the viewport
                        try:
                            filt = _ViewportEventFilter(overlay)
                            vp.installEventFilter(filt)
                            # keep a reference so it's not GC'd
                            setattr(vp, "_overlay_event_filter", filt)
                        except Exception:
                            pass
                    return overlay
                except Exception:
                    return None

            def _show_image_in_view(path: str):
                try:
                    if not path:
                        return
                    pix = QtGui.QPixmap(path)
                    if pix.isNull():
                        print("camera_page: failed to load image", path)
                        return
                    scene = QtWidgets.QGraphicsScene()
                    scene.addPixmap(pix)
                    if cam_view is not None:
                        cam_view.setScene(scene)
                        cam_view.setRenderHints(
                            QtGui.QPainter.RenderHint.SmoothPixmapTransform | QtGui.QPainter.RenderHint.Antialiasing
                        )
                        # fit the image into the view while keeping aspect ratio
                        try:
                            rect = scene.itemsBoundingRect()
                            cam_view.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                        except Exception:
                            pass
                    # send to Roboflow inference asynchronously (if service available)
                    try:
                        if RoboflowClient is not None:
                            # show overlay while inference runs
                            ov = _ensure_overlay()
                            try:
                                if ov is not None:
                                    try:
                                        if getattr(ov, "_spinner", None) is not None:
                                            try:
                                                ov._spinner.start()
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                    ov.show()
                            except Exception:
                                pass

                            class _OverlayNotifier(QtCore.QObject):
                                finished = QtCore.pyqtSignal()

                            notifier = _OverlayNotifier()
                            try:
                                if ov is not None:
                                    def _hide_and_stop():
                                        try:
                                            if getattr(ov, "_spinner", None) is not None:
                                                ov._spinner.stop()
                                        except Exception:
                                            pass
                                        try:
                                            ov.hide()
                                        except Exception:
                                            pass

                                    notifier.finished.connect(_hide_and_stop)
                            except Exception:
                                pass

                            def _run_inference(p, note):
                                try:
                                    client = RoboflowClient.get_default()
                                    print("roboflow: sending image for inference ->", p)
                                    res = client.run_workflow(p)
                                    print("roboflow: inference result:", res)
                                except Exception:
                                    print("roboflow: inference failed:\n", traceback.format_exc())
                                finally:
                                    try:
                                        note.finished.emit()
                                    except Exception:
                                        # fallback: try hiding overlay on main thread
                                        try:
                                            QtCore.QTimer.singleShot(0, lambda: ov.hide() if ov is not None else None)
                                        except Exception:
                                            pass

                            Thread(target=_run_inference, args=(path, notifier), daemon=True).start()
                        else:
                            print("roboflow: service not available (module missing)")
                    except Exception:
                        print("roboflow: failed to start inference thread:\n", traceback.format_exc())
                except Exception as e:
                    print("camera_page: error showing image in view:", e)

            def on_img_upload():
                try:
                    # ask user for image file
                    fname, _ = QtWidgets.QFileDialog.getOpenFileName(
                        camera_page,
                        "Select image",
                        "",
                        "Image Files (*.png *.jpg *.jpeg *.bmp);;All Files (*)",
                    )
                    if fname:
                        _show_image_in_view(fname)
                except Exception as e:
                    print("camera_page: img upload failed:", e)

            if img_btn is not None:
                try:
                    img_btn.clicked.connect(on_img_upload)
                except Exception as e:
                    print("camera_page: failed to connect imgUploadButton:", e)
            else:
                print("camera_page: imgUploadButton not found in UI")
        except Exception as e:
            print("camera_page: error wiring image upload:", e)
        except Exception as e:
            print("camera_page: failed to connect combo signals:", e)

    except Exception as e:
        print("camera_page.setup failed:", e)
