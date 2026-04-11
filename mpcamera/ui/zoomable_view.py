from PyQt6 import QtWidgets, QtCore, QtGui
import logging

logger = logging.getLogger(__name__)


class ZoomableGraphicsView(QtWidgets.QGraphicsView):
    """A QGraphicsView with mouse-wheel zoom (anchor under mouse) and easy panning.

    - Wheel zoom: scale factor per step (configurable)
    - Drag/pan: enabled via DragMode.ScrollHandDrag (left-drag)
    - Methods: zoom_in(), zoom_out(), reset_zoom(), set_pan_enabled(bool)

    Polygons and other QGraphicsItems remain in scene coordinates and will
    automatically move/scale as the view is transformed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom_level = 0
        self._zoom_step = 1.15
        self._zoom_max = 40
        self._zoom_min = -10
        self.setRenderHints(
            self.renderHints()
            | QtGui.QPainter.RenderHint.SmoothPixmapTransform
            | QtGui.QPainter.RenderHint.Antialiasing
        )
        # Keep zoom anchored under the mouse
        try:
            self.setTransformationAnchor(
                QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
            )
            self.setResizeAnchor(
                QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter
            )
        except Exception:
            logger.debug("Could not set transformation anchor", exc_info=True)
        # default to no-pan; enable if user drags (can be toggled)
        try:
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        except Exception:
            logger.debug("Could not set drag mode", exc_info=True)
        try:
            # ensure the view can receive keyboard focus so Space works to toggle pan
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        except Exception:
            logger.debug("Could not set focus policy", exc_info=True)

    def wheelEvent(self, event: QtGui.QWheelEvent):
        # Zoom in/out using wheel; respect limits
        try:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            if delta > 0:
                if self._zoom_level >= self._zoom_max:
                    return
                factor = self._zoom_step
                self._zoom_level += 1
            else:
                if self._zoom_level <= self._zoom_min:
                    return
                factor = 1.0 / self._zoom_step
                self._zoom_level -= 1
            self.scale(factor, factor)
        except Exception:
            logger.debug("wheelEvent error; falling back to base implementation", exc_info=True)
            try:
                super().wheelEvent(event)
            except Exception:
                logger.debug("wheelEvent base fallback also failed")

    def zoom_in(self):
        try:
            if self._zoom_level < self._zoom_max:
                self._zoom_level += 1
                self.scale(self._zoom_step, self._zoom_step)
        except Exception:
            logger.debug("zoom_in failed", exc_info=True)

    def zoom_out(self):
        try:
            if self._zoom_level > self._zoom_min:
                self._zoom_level -= 1
                self.scale(1.0 / self._zoom_step, 1.0 / self._zoom_step)
        except Exception:
            logger.debug("zoom_out failed", exc_info=True)

    def reset_zoom(self):
        try:
            self.resetTransform()
            self._zoom_level = 0
            if self.scene() is not None:
                rect = self.scene().itemsBoundingRect()
                if rect.isValid():
                    self.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        except Exception:
            logger.debug("reset_zoom failed", exc_info=True)

    def set_pan_enabled(self, enabled: bool):
        try:
            if enabled:
                self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            else:
                self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        except Exception:
            logger.debug("set_pan_enabled failed", exc_info=True)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        # double-click resets zoom to fit
        try:
            self.reset_zoom()
        except Exception:
            logger.debug("mouseDoubleClickEvent reset_zoom failed; falling back to base", exc_info=True)
            try:
                super().mouseDoubleClickEvent(event)
            except Exception:
                logger.debug("mouseDoubleClickEvent base fallback also failed")

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        try:
            self.setFocus()
        except Exception:
            logger.debug("mousePressEvent setFocus failed")
        try:
            super().mousePressEvent(event)
        except Exception:
            logger.debug("mousePressEvent base call failed", exc_info=True)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        try:
            if event.key() == QtCore.Qt.Key.Key_Space:
                try:
                    self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
                    vp = self.viewport()
                    try:
                        vp.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                    except Exception:
                        logger.debug("keyPressEvent: could not set closed hand cursor")
                except Exception:
                    logger.debug("keyPressEvent: could not set scroll hand drag mode", exc_info=True)
                return
        except Exception:
            logger.debug("keyPressEvent: Space key handler failed", exc_info=True)
        try:
            super().keyPressEvent(event)
        except Exception:
            logger.debug("keyPressEvent base call failed", exc_info=True)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        try:
            if event.key() == QtCore.Qt.Key.Key_Space:
                try:
                    self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
                    vp = self.viewport()
                    try:
                        vp.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
                    except Exception:
                        logger.debug("keyReleaseEvent: could not restore arrow cursor")
                except Exception:
                    logger.debug("keyReleaseEvent: could not restore NoDrag mode", exc_info=True)
                return
        except Exception:
            logger.debug("keyReleaseEvent: Space key handler failed", exc_info=True)
        try:
            super().keyReleaseEvent(event)
        except Exception:
            logger.debug("keyReleaseEvent base call failed", exc_info=True)
