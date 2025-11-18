from PyQt6 import QtWidgets, QtCore, QtGui
from threading import Thread
import json
import pathlib
import os
import traceback

try:
    from mpcamera.services.roboflow import RoboflowClient
except Exception:
    RoboflowClient = None

# debug log file (repo root)
_log_path = pathlib.Path(__file__).resolve().parents[2] / "prediction_debug.txt"


def _append_log(msg: str):
    try:
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# Utility: deterministic color for a label
def _color_for_label(label: str):
    try:
        if not label:
            return QtGui.QColor(255, 0, 0, 140)
        h = abs(hash(label)) % 360
        c = QtGui.QColor.fromHsv(h, 200, 200, 180)
        return c
    except Exception:
        return QtGui.QColor(255, 0, 0, 140)


class HoverEllipse(QtWidgets.QGraphicsEllipseItem):
    """Ellipse item that shows a translucent fill and a hover label.

    The label is drawn as child items and shown when the mouse hovers.
    """

    def __init__(
        self, x, y, w, h, text="", parent=None, color=QtGui.QColor(255, 0, 0, 140)
    ):
        super().__init__(x, y, w, h, parent)
        self._label_text = text or ""
        self.setAcceptHoverEvents(True)
        self._text_item = None
        self._bg_item = None
        self._color = color

    def hoverEnterEvent(self, event):
        try:
            if self._text_item is None:
                txt = QtWidgets.QGraphicsSimpleTextItem(
                    str(self._label_text), parent=self
                )
                txt.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
                br = txt.boundingRect()
                pad = 4
                rect = QtCore.QRectF(
                    br.x() - pad,
                    br.y() - pad,
                    br.width() + pad * 2,
                    br.height() + pad * 2,
                )
                bg = QtWidgets.QGraphicsRectItem(rect, parent=self)
                bg.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 160)))
                bg.setZValue(self.zValue() + 1)
                txt.setZValue(self.zValue() + 2)
                r = self.rect()
                txt.setPos(r.width() + 6, -(br.height() / 2))
                bg.setPos(txt.pos())
                self._text_item = txt
                self._bg_item = bg
            else:
                try:
                    self._text_item.show()
                except Exception:
                    pass
                try:
                    if self._bg_item is not None:
                        self._bg_item.show()
                except Exception:
                    pass
        except Exception:
            pass
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        try:
            if self._text_item is not None:
                self._text_item.hide()
            if self._bg_item is not None:
                self._bg_item.hide()
        except Exception:
            pass
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget=None):
        try:
            pen = QtGui.QPen(self._color)
            pen.setWidth(2)
            painter.setPen(pen)
            brush = QtGui.QBrush(self._color)
            painter.setBrush(brush)
        except Exception:
            pass
        super().paint(painter, option, widget)


class HoverPolygon(QtWidgets.QGraphicsPolygonItem):
    """Polygon item that shows a translucent fill and a hover label.

    Behaves similarly to HoverEllipse but for arbitrary polygons.
    """

    def __init__(
        self,
        polygon: QtGui.QPolygonF,
        text="",
        parent=None,
        color=QtGui.QColor(255, 0, 0, 140),
    ):
        super().__init__(polygon, parent)
        self._label_text = text or ""
        self.setAcceptHoverEvents(True)
        self._text_item = None
        self._bg_item = None
        self._color = color

    def hoverEnterEvent(self, event):
        try:
            if self._text_item is None:
                txt = QtWidgets.QGraphicsSimpleTextItem(
                    str(self._label_text), parent=self
                )
                txt.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
                br = txt.boundingRect()
                pad = 4
                rect = QtCore.QRectF(
                    br.x() - pad,
                    br.y() - pad,
                    br.width() + pad * 2,
                    br.height() + pad * 2,
                )
                bg = QtWidgets.QGraphicsRectItem(rect, parent=self)
                bg.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 160)))
                bg.setZValue(self.zValue() + 1)
                txt.setZValue(self.zValue() + 2)
                # position label near polygon bounding rect's top-right
                r = self.polygon().boundingRect()
                txt.setPos(r.width() + 6, -(br.height() / 2))
                bg.setPos(txt.pos())
                self._text_item = txt
                self._bg_item = bg
            else:
                try:
                    self._text_item.show()
                except Exception:
                    pass
                try:
                    if self._bg_item is not None:
                        self._bg_item.show()
                except Exception:
                    pass
        except Exception:
            pass
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        try:
            if self._text_item is not None:
                self._text_item.hide()
            if self._bg_item is not None:
                self._bg_item.hide()
        except Exception:
            pass
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget=None):
        try:
            pen = QtGui.QPen(self._color)
            pen.setWidth(2)
            painter.setPen(pen)
            brush = QtGui.QBrush(self._color)
            painter.setBrush(brush)
        except Exception:
            pass
        super().paint(painter, option, widget)


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
                        name = (
                            item.get("site_name")
                            or item.get("name")
                            or item.get("title")
                            or str(item.get("id"))
                        )
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
            print(
                f"Populated soilCombo with {count} entries (filter site_id={site_id})"
            )

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
            if (
                main_window.get_sites() is not None
                and main_window.get_soilsamples() is not None
            ):
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

            # ensure mouse move events are delivered to the view and its viewport
            # so QGraphicsItems that rely on hover events receive them
            try:
                if cam_view is not None:
                    try:
                        cam_view.setMouseTracking(True)
                    except Exception:
                        pass
                    try:
                        vp = cam_view.viewport()
                        if vp is not None:
                            vp.setMouseTracking(True)
                    except Exception:
                        pass
            except Exception:
                pass

            # Create a simple overlay widget that will be shown on top of the camera view
            overlay = None

            class _Spinner(QtWidgets.QWidget):
                def __init__(
                    self,
                    parent=None,
                    diameter=40,
                    line_width=4,
                    color=QtGui.QColor(255, 255, 255),
                ):
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
                    rect = QtCore.QRectF(
                        self._line_width / 2,
                        self._line_width / 2,
                        r.width() - self._line_width,
                        r.height() - self._line_width,
                    )
                    start_angle = int(self._angle * 16)
                    span = int(270 * 16)  # 270 degrees arc
                    painter.drawArc(rect, start_angle, span)

            class _ViewportEventFilter(QtCore.QObject):
                def __init__(self, overlay_widget):
                    super().__init__()
                    self._overlay = overlay_widget

                def eventFilter(self, obj, event):
                    try:
                        if (
                            event.type() == QtCore.QEvent.Type.Resize
                            and self._overlay is not None
                        ):
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
                        overlay.setAttribute(
                            QtCore.Qt.WidgetAttribute.WA_StyledBackground, True
                        )
                        overlay.setStyleSheet(
                            "#camera_loading_overlay { background: rgba(0,0,0,0.5); }"
                        )
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

            # use module-level _color_for_label

            def _show_image_in_view(path: str):
                try:
                    if not path:
                        return
                    print(f"camera_page: _show_image_in_view called with: {path}")
                    pix = QtGui.QPixmap(path)
                    if pix.isNull():
                        print("camera_page: failed to load image", path)
                        return
                    scene = QtWidgets.QGraphicsScene()
                    scene.addPixmap(pix)
                    print("camera_page: pixmap added to scene")
                    if cam_view is not None:
                        cam_view.setScene(scene)
                        cam_view.setRenderHints(
                            QtGui.QPainter.RenderHint.SmoothPixmapTransform
                            | QtGui.QPainter.RenderHint.Antialiasing
                        )
                        try:
                            si = len(scene.items())
                            print(
                                f"camera_page: scene has {si} items after adding pixmap"
                            )
                        except Exception:
                            pass
                        # fit the image into the view while keeping aspect ratio
                        try:
                            rect = scene.itemsBoundingRect()
                            cam_view.fitInView(
                                rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio
                            )
                        except Exception:
                            pass

                    # If the Roboflow service isn't available at runtime, draw some debug overlays
                    # so the developer can verify the drawing code and translucent fill.
                    try:
                        print(
                            f"camera_page: RoboflowClient is {'available' if RoboflowClient is not None else 'MISSING'}"
                        )
                        if (
                            RoboflowClient is None
                            and cam_view is not None
                            and cam_view.scene() is not None
                        ):
                            pix_item = None
                            try:
                                for it in cam_view.scene().items():
                                    try:
                                        from PyQt6 import QtWidgets as _qtw

                                        if isinstance(it, _qtw.QGraphicsPixmapItem):
                                            pix_item = it
                                            break
                                    except Exception:
                                        pass
                            except Exception:
                                pix_item = None
                            if pix_item is not None:
                                print(
                                    "camera_page: found pixmap item for debug overlays"
                                )
                                try:
                                    pix = pix_item.pixmap()
                                    img_w = pix.width()
                                    img_h = pix.height()
                                    pts = [
                                        (img_w * 0.5, img_h * 0.5, "debug_center"),
                                        (img_w * 0.15, img_h * 0.2, "debug_tl"),
                                        (img_w * 0.85, img_h * 0.8, "debug_br"),
                                    ]
                                    for cx_px, cy_px, lab in pts:
                                        try:
                                            r = max(6, int(min(img_w, img_h) * 0.02))
                                            label_text = f"{lab} 1.00"
                                            color = _color_for_label(label_text)
                                            he = HoverEllipse(
                                                cx_px - r,
                                                cy_px - r,
                                                r * 2,
                                                r * 2,
                                                text=label_text,
                                                color=color,
                                            )
                                            he.setZValue(20)
                                            try:
                                                he.setData(0, "inference_overlay")
                                            except Exception:
                                                pass
                                            cam_view.scene().addItem(he)
                                            print(
                                                f"camera_page: added debug overlay '{label_text}' at ({cx_px:.1f},{cy_px:.1f})"
                                            )
                                            try:
                                                _append_log(
                                                    f"ADDED DEBUG OVERLAY: {label_text} at ({cx_px:.1f},{cy_px:.1f})"
                                                )
                                            except Exception:
                                                pass
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
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
                                # emit the inference result object when ready
                                finished = QtCore.pyqtSignal(object)

                            notifier = _OverlayNotifier()

                            def _handle_inference_result(result):
                                # hide overlay and stop spinner, then draw overlays on the scene
                                try:
                                    try:
                                        if getattr(ov, "_spinner", None) is not None:
                                            ov._spinner.stop()
                                    except Exception:
                                        pass
                                    try:
                                        ov.hide()
                                    except Exception:
                                        pass
                                except Exception:
                                    pass

                                # draw points and labels on the scene (main thread)
                                try:
                                    scene = None
                                    if cam_view is not None:
                                        scene = cam_view.scene()
                                    if scene is None:
                                        return

                                    # find the pixmap item (the base image)
                                    pix_item = None
                                    for it in scene.items():
                                        # QGraphicsPixmapItem is available on QtWidgets
                                        try:
                                            from PyQt6 import QtWidgets as _qtw

                                            if isinstance(it, _qtw.QGraphicsPixmapItem):
                                                pix_item = it
                                                break
                                        except Exception:
                                            pass
                                    if pix_item is None:
                                        return
                                    pix = pix_item.pixmap()
                                    img_w = pix.width()
                                    img_h = pix.height()

                                    # remove previous inference overlays (mark with data key)
                                    try:
                                        for it in list(scene.items()):
                                            try:
                                                if it.data(0) == "inference_overlay":
                                                    scene.removeItem(it)
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass

                                    # helper to find predictions list inside result
                                    def _find_predictions(obj):
                                        if obj is None:
                                            return []
                                        if (
                                            isinstance(obj, list)
                                            and obj
                                            and isinstance(obj[0], dict)
                                        ):
                                            return obj
                                        if isinstance(obj, dict):
                                            # common keys
                                            for k in (
                                                "predictions",
                                                "preds",
                                                "outputs",
                                                "results",
                                                "objects",
                                            ):
                                                v = obj.get(k)
                                                if (
                                                    isinstance(v, list)
                                                    and v
                                                    and isinstance(v[0], dict)
                                                ):
                                                    return v
                                            # search deeper
                                            for v in obj.values():
                                                p = _find_predictions(v)
                                                if p:
                                                    return p
                                        return []

                                    def _extract_points_from_prediction(pred):
                                        """Try multiple known keys/formats to extract a list of (x,y) coords.

                                        Returns empty list when none found.
                                        """
                                        try:
                                            # common keys that may contain point lists
                                            for key in (
                                                "points",
                                                "polygon",
                                                "poly",
                                                "shape",
                                            ):
                                                if key in pred:
                                                    pts = pred.get(key)
                                                    # nested dict with 'data'
                                                    if (
                                                        isinstance(pts, dict)
                                                        and "data" in pts
                                                    ):
                                                        pts = pts.get("data")
                                                    # flat list of numbers
                                                    if (
                                                        isinstance(pts, (list, tuple))
                                                        and pts
                                                    ):
                                                        # detect a flat numeric list [x,y,x,y,...]
                                                        if all(
                                                            isinstance(v, (int, float))
                                                            for v in pts
                                                        ):
                                                            it = iter(pts)
                                                            out = []
                                                            for x in it:
                                                                try:
                                                                    y = next(it)
                                                                except StopIteration:
                                                                    break
                                                                out.append(
                                                                    (float(x), float(y))
                                                                )
                                                            if out:
                                                                return out
                                                        # list of [x,y] or {'x':..,'y':..}
                                                        out = []
                                                        for item in pts:
                                                            try:
                                                                if (
                                                                    isinstance(
                                                                        item, dict
                                                                    )
                                                                    and "x" in item
                                                                    and "y" in item
                                                                ):
                                                                    out.append(
                                                                        (
                                                                            float(
                                                                                item.get(
                                                                                    "x"
                                                                                )
                                                                            ),
                                                                            float(
                                                                                item.get(
                                                                                    "y"
                                                                                )
                                                                            ),
                                                                        )
                                                                    )
                                                                elif (
                                                                    isinstance(
                                                                        item,
                                                                        (list, tuple),
                                                                    )
                                                                    and len(item) >= 2
                                                                    and isinstance(
                                                                        item[0],
                                                                        (int, float),
                                                                    )
                                                                ):
                                                                    out.append(
                                                                        (
                                                                            float(
                                                                                item[0]
                                                                            ),
                                                                            float(
                                                                                item[1]
                                                                            ),
                                                                        )
                                                                    )
                                                            except Exception:
                                                                continue
                                                        if out:
                                                            return out
                                            # segmentation (COCO style) may be nested lists or flat
                                            if "segmentation" in pred:
                                                seg = pred.get("segmentation")
                                                if isinstance(seg, list) and seg:
                                                    flat = None
                                                    first = seg[0]
                                                    if isinstance(
                                                        first, (list, tuple)
                                                    ) and all(
                                                        isinstance(v, (int, float))
                                                        for v in first
                                                    ):
                                                        flat = first
                                                    elif all(
                                                        isinstance(v, (int, float))
                                                        for v in seg
                                                    ):
                                                        flat = seg
                                                    if flat:
                                                        out = []
                                                        it = iter(flat)
                                                        for x in it:
                                                            try:
                                                                y = next(it)
                                                            except StopIteration:
                                                                break
                                                            out.append(
                                                                (float(x), float(y))
                                                            )
                                                        if out:
                                                            return out
                                            # bbox list [x,y,w,h]
                                            if "bbox" in pred and isinstance(
                                                pred.get("bbox"), (list, tuple)
                                            ):
                                                bb = pred.get("bbox")
                                                try:
                                                    bx = float(bb[0])
                                                    by = float(bb[1])
                                                    bw = float(bb[2])
                                                    bh = float(bb[3])
                                                    return [
                                                        (bx, by),
                                                        (bx + bw, by),
                                                        (bx + bw, by + bh),
                                                        (bx, by + bh),
                                                    ]
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                                        return []

                                    preds = _find_predictions(result)
                                    # Some inference responses wrap the real prediction dicts
                                    # inside another dict under keys like 'predictions' or
                                    # 'outputs'. Normalize (flatten) those wrappers so the
                                    # rest of the code can operate on actual prediction dicts.
                                    flat_preds = []
                                    try:
                                        for item in preds:
                                            # case 1: item directly contains a list under a known key
                                            found = False
                                            if isinstance(item, dict):
                                                for k in (
                                                    "predictions",
                                                    "outputs",
                                                    "results",
                                                    "objects",
                                                ):
                                                    v = item.get(k)
                                                    # nested list directly
                                                    if (
                                                        isinstance(v, list)
                                                        and v
                                                        and isinstance(v[0], dict)
                                                    ):
                                                        flat_preds.extend(v)
                                                        found = True
                                                        break
                                                    # nested dict that itself contains the list
                                                    if isinstance(v, dict):
                                                        for kk in (
                                                            "predictions",
                                                            "outputs",
                                                            "results",
                                                            "objects",
                                                            "data",
                                                        ):
                                                            vv = v.get(kk)
                                                            if (
                                                                isinstance(vv, list)
                                                                and vv
                                                                and isinstance(
                                                                    vv[0], dict
                                                                )
                                                            ):
                                                                flat_preds.extend(vv)
                                                                found = True
                                                                break
                                                        if found:
                                                            break
                                            if not found:
                                                flat_preds.append(item)
                                    except Exception:
                                        flat_preds = preds

                                    preds = flat_preds
                                    print(
                                        f"camera_page: found {len(preds)} predictions (flattened)"
                                    )
                                    try:
                                        _append_log(f"FOUND PREDICTIONS: {len(preds)}")
                                    except Exception:
                                        pass

                                    for p in preds:
                                        try:
                                            print(f"camera_page: prediction raw: {p}")
                                            try:
                                                _append_log(
                                                    "PRED RAW: "
                                                    + json.dumps(p, default=str)
                                                )
                                            except Exception:
                                                _append_log("PRED RAW: " + str(p))
                                            # determine label and score
                                            label = (
                                                p.get("class")
                                                or p.get("label")
                                                or p.get("predicted_class")
                                                or p.get("name")
                                                or str(p.get("id", ""))
                                            )
                                            score = (
                                                p.get("confidence")
                                                or p.get("score")
                                                or p.get("confidence_score")
                                            )

                                            # find a point (x,y) or bbox
                                            cx = None
                                            cy = None
                                            # direct x/y
                                            if "x" in p and "y" in p:
                                                cx = p.get("x")
                                                cy = p.get("y")
                                            # bbox center
                                            elif "bbox" in p and isinstance(
                                                p.get("bbox"), dict
                                            ):
                                                bb = p.get("bbox")
                                                bx = bb.get("x")
                                                by = bb.get("y")
                                                bw = (
                                                    bb.get("w")
                                                    or bb.get("width")
                                                    or bb.get("w", 0)
                                                )
                                                bh = (
                                                    bb.get("h")
                                                    or bb.get("height")
                                                    or bb.get("h", 0)
                                                )
                                                if bx is not None and by is not None:
                                                    # some bboxes are top-left x,y; center them
                                                    try:
                                                        bx_f = float(bx)
                                                        by_f = float(by)
                                                        bw_f = (
                                                            float(bw)
                                                            if bw is not None
                                                            else 0
                                                        )
                                                        bh_f = (
                                                            float(bh)
                                                            if bh is not None
                                                            else 0
                                                        )
                                                        cx = bx_f + bw_f / 2.0
                                                        cy = by_f + bh_f / 2.0
                                                    except Exception:
                                                        cx = None
                                                        cy = None
                                            # try to extract polygon/points from prediction in many formats
                                            pts_found = []
                                            try:
                                                pts_found = (
                                                    _extract_points_from_prediction(p)
                                                )
                                                # sometimes the prediction dict itself contains a
                                                # nested container under a key like 'predictions'
                                                # that carries the points. Try a shallow fallback.
                                                if not pts_found and isinstance(
                                                    p, dict
                                                ):
                                                    for k in (
                                                        "predictions",
                                                        "outputs",
                                                        "results",
                                                        "objects",
                                                    ):
                                                        v = p.get(k)
                                                        if isinstance(v, list) and v:
                                                            # try first element
                                                            try:
                                                                pts_found = (
                                                                    _extract_points_from_prediction(
                                                                        v[0]
                                                                    )
                                                                    or pts_found
                                                                )
                                                            except Exception:
                                                                pass
                                                            if pts_found:
                                                                break
                                            except Exception:
                                                pts_found = []
                                            if pts_found:
                                                try:
                                                    is_norm = all(
                                                        0.0 <= xx <= 1.0
                                                        and 0.0 <= yy <= 1.0
                                                        for xx, yy in pts_found
                                                    )
                                                    if is_norm:
                                                        coords_px = [
                                                            (xx * img_w, yy * img_h)
                                                            for xx, yy in pts_found
                                                        ]
                                                    else:
                                                        coords_px = pts_found
                                                    poly = QtGui.QPolygonF()
                                                    for xx, yy in coords_px:
                                                        poly.append(
                                                            QtCore.QPointF(xx, yy)
                                                        )
                                                    label_text = (
                                                        str(label)
                                                        if label is not None
                                                        else ""
                                                    )
                                                    if score is not None:
                                                        try:
                                                            sc = float(score)
                                                            label_text = (
                                                                f"{label_text} {sc:.2f}"
                                                            )
                                                        except Exception:
                                                            label_text = (
                                                                f"{label_text} {score}"
                                                            )
                                                    color = _color_for_label(label_text)
                                                    hp = HoverPolygon(
                                                        poly,
                                                        text=label_text,
                                                        color=color,
                                                    )
                                                    hp.setZValue(20)
                                                    try:
                                                        hp.setData(
                                                            0, "inference_overlay"
                                                        )
                                                    except Exception:
                                                        pass
                                                    scene.addItem(hp)
                                                    print(
                                                        f"camera_page: added polygon overlay for '{label_text}' with {len(coords_px)} points"
                                                    )
                                                    try:
                                                        _append_log(
                                                            "ADDED POLYGON: "
                                                            + json.dumps(
                                                                {
                                                                    "label": label_text,
                                                                    "points": coords_px,
                                                                },
                                                                default=str,
                                                            )
                                                        )
                                                    except Exception:
                                                        pass
                                                    continue
                                                except Exception:
                                                    # ensure the try has an except to avoid SyntaxError and
                                                    # allow processing to continue to other prediction types
                                                    pass
                                            # end pts_found handling

                                            if cx is None or cy is None:
                                                # if no point or bbox, log keys to help debugging
                                                try:
                                                    keys = (
                                                        list(p.keys())
                                                        if isinstance(p, dict)
                                                        else str(type(p))
                                                    )
                                                except Exception:
                                                    keys = "<unreadable>"
                                                print(
                                                    f"camera_page: skipping prediction because no coords found (cx={cx}, cy={cy}) — keys={keys}"
                                                )
                                                try:
                                                    _append_log(
                                                        f"SKIPPED PRED: keys={keys} raw={json.dumps(p, default=str)[:800]}"
                                                    )
                                                except Exception:
                                                    pass
                                                continue

                                            # convert normalized coords to pixel if needed
                                            try:
                                                cx_f = float(cx)
                                                cy_f = float(cy)
                                            except Exception:
                                                continue
                                            if 0 <= cx_f <= 1 and 0 <= cy_f <= 1:
                                                cx_px = cx_f * img_w
                                                cy_px = cy_f * img_h
                                            else:
                                                cx_px = cx_f
                                                cy_px = cy_f
                                            print(
                                                f"camera_page: computed pixel coords: ({cx_px},{cy_px}) from raw ({cx},{cy})"
                                            )

                                            # draw circle with HoverEllipse (shows label on hover)
                                            r = max(6, int(min(img_w, img_h) * 0.02))
                                            label_text = (
                                                str(label) if label is not None else ""
                                            )
                                            if score is not None:
                                                try:
                                                    sc = float(score)
                                                    label_text = (
                                                        f"{label_text} {sc:.2f}"
                                                    )
                                                except Exception:
                                                    label_text = f"{label_text} {score}"

                                            color = _color_for_label(label_text)
                                            he = HoverEllipse(
                                                cx_px - r,
                                                cy_px - r,
                                                r * 2,
                                                r * 2,
                                                text=label_text,
                                                color=color,
                                            )
                                            he.setZValue(20)
                                            try:
                                                he.setData(0, "inference_overlay")
                                            except Exception:
                                                pass
                                            scene.addItem(he)
                                            print(
                                                f"camera_page: added overlay for '{label_text}' at ({cx_px:.1f},{cy_px:.1f})"
                                            )
                                            try:
                                                _append_log(
                                                    f"ADDED OVERLAY: {label_text} at ({cx_px:.1f},{cy_px:.1f})"
                                                )
                                            except Exception:
                                                pass
                                        except Exception:
                                            pass
                                except Exception:
                                    pass

                            notifier.finished.connect(_handle_inference_result)

                            def _run_inference(p, note):
                                res = None
                                try:
                                    client = RoboflowClient.get_default()
                                    print("roboflow: sending image for inference ->", p)
                                    res = client.run_workflow(p)
                                    print("roboflow: inference result:", res)
                                except Exception:
                                    print(
                                        "roboflow: inference failed:\n",
                                        traceback.format_exc(),
                                    )
                                finally:
                                    try:
                                        note.finished.emit(res)
                                    except Exception:
                                        # fallback: try hiding overlay on main thread
                                        try:
                                            QtCore.QTimer.singleShot(
                                                0,
                                                lambda: (
                                                    ov.hide()
                                                    if ov is not None
                                                    else None
                                                ),
                                            )
                                        except Exception:
                                            pass

                            Thread(
                                target=_run_inference,
                                args=(path, notifier),
                                daemon=True,
                            ).start()
                        else:
                            print("roboflow: service not available (module missing)")
                    except Exception:
                        print(
                            "roboflow: failed to start inference thread:\n",
                            traceback.format_exc(),
                        )
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
        print("camera_page.setup failed:", e)
