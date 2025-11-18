from PyQt6 import QtWidgets, QtCore, QtGui
from mpcamera.utils.camera_utils import append_log, color_for_label
from mpcamera.utils.prediction_utils import (
    find_predictions,
    extract_points_from_prediction,
)
import json


# Preferred class colors (semi-translucent)
_CLASS_COLOR_MAP = {
    "sheet": QtGui.QColor(50, 130, 255, 160),
    "fragment": QtGui.QColor(220, 50, 50, 160),
    "fiber": QtGui.QColor(150, 63, 255, 160),
    "bead": QtGui.QColor(255, 165, 0, 160),
    "foam": QtGui.QColor(0, 200, 160, 160),
    "film": QtGui.QColor(60, 180, 75, 160),
}


def _color_for_class(label, fallback_text=None):
    try:
        if not label:
            return color_for_label(fallback_text or "")
        key = str(label).strip().lower()
        c = _CLASS_COLOR_MAP.get(key)
        if c is not None:
            return c
    except Exception:
        pass
    return color_for_label(fallback_text or label)


class OverlaySpinner(QtWidgets.QWidget):
    def __init__(
        self, parent=None, diameter=40, line_width=4, color=QtGui.QColor(255, 255, 255)
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
        rect = QtCore.QRectF(
            self._line_width / 2,
            self._line_width / 2,
            r.width() - self._line_width,
            r.height() - self._line_width,
        )
        start_angle = int(self._angle * 16)
        span = int(270 * 16)
        painter.drawArc(rect, start_angle, span)


class ViewportEventFilter(QtCore.QObject):
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


def ensure_overlay_for_view(cam_view: QtWidgets.QGraphicsView):
    """Create (or return) an overlay widget attached to the view's viewport.

    The overlay will contain a spinner at center and be hidden by default.
    """
    try:
        if cam_view is None:
            return None
        vp = cam_view.viewport()
        if vp is None:
            return None
        existing = getattr(vp, "_camera_overlay", None)
        if existing is not None:
            return existing

        overlay = QtWidgets.QWidget(vp)
        overlay.setObjectName("camera_loading_overlay")
        overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        overlay.setStyleSheet(
            "#camera_loading_overlay { background: rgba(0,0,0,0.5); }"
        )
        lay = QtWidgets.QVBoxLayout(overlay)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        spinner = OverlaySpinner(overlay, diameter=36, line_width=4)
        lay.addWidget(spinner, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        overlay._spinner = spinner
        overlay.setGeometry(vp.rect())
        overlay.hide()
        try:
            filt = ViewportEventFilter(overlay)
            vp.installEventFilter(filt)
            setattr(vp, "_overlay_event_filter", filt)
        except Exception:
            pass
        setattr(vp, "_camera_overlay", overlay)
        return overlay
    except Exception:
        return None


class HoverEllipse(QtWidgets.QGraphicsEllipseItem):
    def __init__(
        self, x, y, w, h, text="", parent=None, color=QtGui.QColor(255, 0, 0, 140)
    ):
        super().__init__(x, y, w, h, parent)
        self._label_text = text or ""
        # show label always on top of shape; still accept hover for tooltip
        self.setAcceptHoverEvents(True)
        self._color = color
        # create text + background immediately and position at center
        try:
            txt = QtWidgets.QGraphicsSimpleTextItem(str(self._label_text), parent=self)
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
            # center label over the ellipse
            txt.setPos(
                r.x() + r.width() / 2 - br.width() / 2,
                r.y() + r.height() / 2 - br.height() / 2,
            )
            bg.setPos(txt.pos())
            self._text_item = txt
            self._bg_item = bg
        except Exception:
            self._text_item = None
            self._bg_item = None
        try:
            # ensure brush/pen are set so the item is filled with translucent color
            brush = QtGui.QBrush(self._color)
            brush.setStyle(QtCore.Qt.BrushStyle.SolidPattern)
            self.setBrush(brush)
            pen = QtGui.QPen(self._color.darker(110))
            pen.setWidth(2)
            self.setPen(pen)
        except Exception:
            pass

    def hoverEnterEvent(self, event):
        # tooltip handled via setToolTip; label is always visible
        super().hoverEnterEvent(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        # label is persistent; nothing to hide on leave
        super().hoverLeaveEvent(event)
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget=None):
        try:
            # draw a translucent fill with a slightly darker outline
            pen = QtGui.QPen(self._color.darker(110))
            pen.setWidth(2)
            painter.setPen(pen)
            brush = QtGui.QBrush(self._color)
            painter.setBrush(brush)
        except Exception:
            pass
        super().paint(painter, option, widget)


class HoverPolygon(QtWidgets.QGraphicsPolygonItem):
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
        self._color = color
        # create label and background centered on polygon
        try:
            txt = QtWidgets.QGraphicsSimpleTextItem(str(self._label_text), parent=self)
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
            r = self.polygon().boundingRect()
            txt.setPos(
                r.x() + r.width() / 2 - br.width() / 2,
                r.y() + r.height() / 2 - br.height() / 2,
            )
            bg.setPos(txt.pos())
            self._text_item = txt
            self._bg_item = bg
        except Exception:
            self._text_item = None
            self._bg_item = None
        try:
            brush = QtGui.QBrush(self._color)
            brush.setStyle(QtCore.Qt.BrushStyle.SolidPattern)
            self.setBrush(brush)
            pen = QtGui.QPen(self._color.darker(110))
            pen.setWidth(2)
            self.setPen(pen)
        except Exception:
            pass

    def hoverEnterEvent(self, event):
        # label is persistent; tooltip is provided separately
        super().hoverEnterEvent(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        super().hoverLeaveEvent(event)
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget=None):
        try:
            pen = QtGui.QPen(self._color.darker(110))
            pen.setWidth(2)
            painter.setPen(pen)
            brush = QtGui.QBrush(self._color)
            painter.setBrush(brush)
        except Exception:
            pass
        super().paint(painter, option, widget)


def show_debug_overlays(
    scene: QtWidgets.QGraphicsScene, pix_item: QtWidgets.QGraphicsPixmapItem
):
    try:
        if scene is None or pix_item is None:
            return
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
                color = color_for_label(label_text)
                he = HoverEllipse(
                    cx_px - r, cy_px - r, r * 2, r * 2, text=label_text, color=color
                )
                he.setZValue(20)
                try:
                    he.setData(0, "inference_overlay")
                except Exception:
                    pass
                scene.addItem(he)
                try:
                    append_log(
                        f"ADDED DEBUG OVERLAY: {label_text} at ({cx_px:.1f},{cy_px:.1f})"
                    )
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass


def render_predictions_on_scene(scene: QtWidgets.QGraphicsScene, result):
    try:
        if scene is None:
            return
        # find the pixmap item
        pix_item = None
        for it in scene.items():
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

        # remove previous inference overlays
        try:
            for it in list(scene.items()):
                try:
                    if it.data(0) == "inference_overlay":
                        scene.removeItem(it)
                except Exception:
                    pass
        except Exception:
            pass

        preds = find_predictions(result)
        # flatten wrappers similar to previous controller logic
        flat_preds = []
        try:
            for item in preds:
                found = False
                if isinstance(item, dict):
                    for k in ("predictions", "outputs", "results", "objects"):
                        v = item.get(k)
                        if isinstance(v, list) and v and isinstance(v[0], dict):
                            flat_preds.extend(v)
                            found = True
                            break
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
                                    and isinstance(vv[0], dict)
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
        try:
            append_log(f"FOUND PREDICTIONS: {len(preds)}")
        except Exception:
            pass

        for p in preds:
            try:
                try:
                    append_log("PRED RAW: " + json.dumps(p, default=str))
                except Exception:
                    try:
                        append_log("PRED RAW: " + str(p))
                    except Exception:
                        pass

                label = (
                    p.get("class")
                    or p.get("label")
                    or p.get("predicted_class")
                    or p.get("name")
                    or str(p.get("id", ""))
                )
                score = (
                    p.get("confidence") or p.get("score") or p.get("confidence_score")
                )

                cx = None
                cy = None
                if "x" in p and "y" in p:
                    cx = p.get("x")
                    cy = p.get("y")
                elif "bbox" in p and isinstance(p.get("bbox"), dict):
                    bb = p.get("bbox")
                    bx = bb.get("x")
                    by = bb.get("y")
                    bw = bb.get("w") or bb.get("width") or bb.get("w", 0)
                    bh = bb.get("h") or bb.get("height") or bb.get("h", 0)
                    if bx is not None and by is not None:
                        try:
                            bx_f = float(bx)
                            by_f = float(by)
                            bw_f = float(bw) if bw is not None else 0
                            bh_f = float(bh) if bh is not None else 0
                            cx = bx_f + bw_f / 2.0
                            cy = by_f + bh_f / 2.0
                        except Exception:
                            cx = None
                            cy = None

                pts_found = []
                try:
                    pts_found = extract_points_from_prediction(p)
                    if not pts_found and isinstance(p, dict):
                        for k in ("predictions", "outputs", "results", "objects"):
                            v = p.get(k)
                            if isinstance(v, list) and v:
                                try:
                                    pts_found = (
                                        extract_points_from_prediction(v[0])
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
                            0.0 <= xx <= 1.0 and 0.0 <= yy <= 1.0
                            for xx, yy in pts_found
                        )
                        if is_norm:
                            coords_px = [
                                (xx * img_w, yy * img_h) for xx, yy in pts_found
                            ]
                        else:
                            coords_px = pts_found
                        poly = QtGui.QPolygonF()
                        for xx, yy in coords_px:
                            poly.append(QtCore.QPointF(xx, yy))
                        label_text = str(label) if label is not None else ""
                        if score is not None:
                            try:
                                sc = float(score)
                                label_text = f"{label_text} {sc:.2f}"
                            except Exception:
                                label_text = f"{label_text} {score}"
                        color = color_for_label(label_text)
                        # prefer class-specific colors when possible
                        color = _color_for_class(label, fallback_text=label_text)
                        hp = HoverPolygon(poly, text=label_text, color=color)
                        hp.setZValue(20)
                        try:
                            hp.setData(0, "inference_overlay")
                        except Exception:
                            pass
                        # set tooltip with class and confidence
                        try:
                            if score is not None:
                                sc = float(score)
                                hp.setToolTip(f"Class: {label}\nConfidence: {sc:.2f}")
                            else:
                                hp.setToolTip(f"Class: {label}")
                        except Exception:
                            try:
                                hp.setToolTip(str(label_text))
                            except Exception:
                                pass
                        scene.addItem(hp)
                        try:
                            append_log(
                                "ADDED POLYGON: "
                                + json.dumps(
                                    {"label": label_text, "points": coords_px},
                                    default=str,
                                )
                            )
                        except Exception:
                            pass
                        continue
                    except Exception:
                        pass

                if cx is None or cy is None:
                    try:
                        keys = list(p.keys()) if isinstance(p, dict) else str(type(p))
                    except Exception:
                        keys = "<unreadable>"
                    try:
                        append_log(
                            f"SKIPPED PRED: keys={keys} raw={json.dumps(p, default=str)[:800]}"
                        )
                    except Exception:
                        pass
                    continue

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

                r = max(6, int(min(img_w, img_h) * 0.02))
                label_text = str(label) if label is not None else ""
                if score is not None:
                    try:
                        sc = float(score)
                        label_text = f"{label_text} {sc:.2f}"
                    except Exception:
                        label_text = f"{label_text} {score}"

                color = color_for_label(label_text)
                color = _color_for_class(label, fallback_text=label_text)
                he = HoverEllipse(
                    cx_px - r, cy_px - r, r * 2, r * 2, text=label_text, color=color
                )
                he.setZValue(20)
                try:
                    he.setData(0, "inference_overlay")
                except Exception:
                    pass
                try:
                    if score is not None:
                        sc = float(score)
                        he.setToolTip(f"Class: {label}\nConfidence: {sc:.2f}")
                    else:
                        he.setToolTip(f"Class: {label}")
                except Exception:
                    try:
                        he.setToolTip(str(label_text))
                    except Exception:
                        pass
                scene.addItem(he)
                try:
                    append_log(
                        f"ADDED OVERLAY: {label_text} at ({cx_px:.1f},{cy_px:.1f})"
                    )
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass
