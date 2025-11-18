from PyQt6 import QtWidgets, QtCore, QtGui


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
            pass
        # default to no-pan; enable if user drags (can be toggled)
        try:
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        except Exception:
            pass
        try:
            # ensure the view can receive keyboard focus so Space works to toggle pan
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        except Exception:
            pass

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
            # fallback to base implementation
            try:
                super().wheelEvent(event)
            except Exception:
                pass

    def zoom_in(self):
        try:
            if self._zoom_level < self._zoom_max:
                self._zoom_level += 1
                self.scale(self._zoom_step, self._zoom_step)
        except Exception:
            pass

    def zoom_out(self):
        try:
            if self._zoom_level > self._zoom_min:
                self._zoom_level -= 1
                self.scale(1.0 / self._zoom_step, 1.0 / self._zoom_step)
        except Exception:
            pass

    def reset_zoom(self):
        try:
            self.resetTransform()
            self._zoom_level = 0
            if self.scene() is not None:
                rect = self.scene().itemsBoundingRect()
                if rect.isValid():
                    self.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        except Exception:
            pass

    def set_pan_enabled(self, enabled: bool):
        try:
            if enabled:
                self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            else:
                self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        except Exception:
            pass

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        # double-click resets zoom to fit
        try:
            self.reset_zoom()
        except Exception:
            try:
                super().mouseDoubleClickEvent(event)
            except Exception:
                pass

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        try:
            # ensure the view receives focus when clicked so key events are delivered
            try:
                self.setFocus()
            except Exception:
                pass
        except Exception:
            pass
        try:
            super().mousePressEvent(event)
        except Exception:
            pass

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        try:
            if event.key() == QtCore.Qt.Key.Key_Space:
                try:
                    self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
                    vp = self.viewport()
                    try:
                        vp.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                    except Exception:
                        pass
                except Exception:
                    pass
                # consume the event
                return
        except Exception:
            pass
        try:
            super().keyPressEvent(event)
        except Exception:
            pass

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        try:
            if event.key() == QtCore.Qt.Key.Key_Space:
                try:
                    self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
                    vp = self.viewport()
                    try:
                        vp.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
                    except Exception:
                        pass
                except Exception:
                    pass
                return
        except Exception:
            pass
        try:
            super().keyReleaseEvent(event)
        except Exception:
            pass
