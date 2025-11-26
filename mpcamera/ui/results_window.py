import os
from PyQt6 import uic, QtWidgets, QtCore, QtGui
from mpcamera.utils.results_manager import ResultsManager
from mpcamera.utils.color_utils import get_color_name

# --- CONSTANTS ---
MICROPLASTIC_TYPES = ["Fragment", "Fiber", "Foam", "Film", "Pellet", "Sheet", "Bead"]


class _PreviewController(QtCore.QObject):
    """
    Helper to add zoom/pan behavior to a QGraphicsView.
    Handles mouse wheel zooming and click-and-drag panning.
    """

    def __init__(self, view: QtWidgets.QGraphicsView):
        super().__init__(view)
        self.view = view
        self.scene = QtWidgets.QGraphicsScene(self.view)
        self.view.setScene(self.scene)
        self.pixmap_item = None
        self._zoom = 1.0

        # Optimization: Smooth transformation
        try:
            self.view.setRenderHint(
                QtGui.QPainter.RenderHint.SmoothPixmapTransform, True
            )
            self.view.viewport().installEventFilter(self)
        except Exception:
            pass

    def setPixmap(self, pixmap: QtGui.QPixmap):
        try:
            self.scene.clear()
            self.pixmap_item = self.scene.addPixmap(pixmap)
            self.scene.setSceneRect(self.pixmap_item.boundingRect())
            self._zoom = 1.0
            self.fit()
        except Exception:
            pass

    def fit(self):
        try:
            if self.pixmap_item is None:
                return
            self.view.resetTransform()
            self.view.fitInView(
                self.pixmap_item, QtCore.Qt.AspectRatioMode.KeepAspectRatio
            )
            self._zoom = 1.0
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            if event.type() == QtCore.QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                if delta == 0:
                    return False

                # Zoom In / Out Logic
                factor = 1.15 if delta > 0 else 1.0 / 1.15

                # Zoom around mouse cursor
                old_pos = self.view.mapToScene(event.position().toPoint())
                self.view.scale(factor, factor)
                self._zoom *= factor
                new_pos = self.view.mapToScene(event.position().toPoint())
                diff = new_pos - old_pos
                self.view.translate(diff.x(), diff.y())
                return True
        except Exception:
            pass
        return super().eventFilter(obj, event)


class ResultsWindow(QtWidgets.QMainWindow):
    # Signal to send validated data back to main app
    # Payload: List of dictionaries (morphometrics + verified labels)
    data_committed = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- 1. Load UI File ---
        ui_path = os.path.join(
            os.path.dirname(__file__), "..", "layouts", "resultsWindow.ui"
        )
        try:
            uic.loadUi(ui_path, self)
        except Exception as e:
            print(f"Error loading UI: {e}")
            # Fallback resize if XML fails completely
            self.resize(1200, 700)

        # --- 2. Widget References ---
        self.table: QtWidgets.QTableWidget = getattr(self, "resultsTable", None)
        self.preview_view: QtWidgets.QGraphicsView = getattr(self, "previewView", None)
        self.btn_delete: QtWidgets.QPushButton = getattr(self, "btnDelete", None)
        self.btn_save: QtWidgets.QPushButton = getattr(self, "btnSave", None)
        self.splitter: QtWidgets.QSplitter = getattr(self, "splitter", None)

        # --- 3. Setup Graphics View (The Fix for PyQt6 Enums) ---
        if self.preview_view is not None:
            # We set these in Python to avoid XML errors with "ScrollHandDrag"
            self.preview_view.setDragMode(
                QtWidgets.QGraphicsView.DragMode.ScrollHandDrag
            )
            self.preview_view.setTransformationAnchor(
                QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
            )
            self.preview_view.setResizeAnchor(
                QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
            )

            # Initialize Controller
            self._preview_ctrl = _PreviewController(self.preview_view)

        # --- 4. Setup Table Columns ---
        if self.table:
            # We need 10 columns total now:
            # 0:ID, 1:Class, 2:Conf, 3:Color, 4:Area, 5:Perim, 6:Major, 7:Minor, 8:Deq, 9:Skel
            desired_headers = [
                "ID",
                "Class",
                "Confidence",
                "Color",
                "Area",
                "Perim",
                "Major",
                "Minor",
                "Deq",
                "Skeleton",
            ]

            # If XML has fewer columns, expand it automatically
            if self.table.columnCount() < len(desired_headers):
                self.table.setColumnCount(len(desired_headers))
                self.table.setHorizontalHeaderLabels(desired_headers)

            self.table.setColumnHidden(0, True)  # Hide ID column
            self.table.itemSelectionChanged.connect(self._on_selection_changed)

        # --- 5. Button Connections ---
        if self.btn_delete:
            self.btn_delete.clicked.connect(self.delete_selected_row)
        if self.btn_save:
            self.btn_save.clicked.connect(self.emit_save_data)

        # --- Internal State ---
        self._last_pixmap = None
        self._cached_morphometrics = []  # Stores the master list of data dicts

    def update_data(self, preds, last_pixmap, current_frame_np):
        """
        Main entry point. Populates the table with inference results.
        """
        self._last_pixmap = last_pixmap
        self._cached_morphometrics = []  # Reset cache

        if self.table is None:
            return

        self.table.setRowCount(0)
        self.table.setSortingEnabled(False)  # Disable sorting during insertion

        if not preds:
            if self._preview_ctrl:
                self._preview_ctrl.scene.clear()
            return

        for i, p in enumerate(preds):
            self.table.insertRow(i)

            # --- A. Calculate Data ---
            w = last_pixmap.width()
            h = last_pixmap.height()

            # Use your utility class for math
            stats = ResultsManager.calculate_morphometrics(p, w, h, magnification=1.0)

            # Color detection logic
            color_name = "Unknown"
            if current_frame_np is not None:
                try:
                    pts = p.get("points", [])
                    if pts:
                        color_name = get_color_name(current_frame_np, pts)
                except Exception:
                    pass

            # Create Master Record
            full_record = {
                **p,
                **stats,
                "color_name": color_name,
                "verification": "model_prediction",  # Default status tag
                "label": p.get("label", "Fragment"),  # Ensure label exists
            }
            self._cached_morphometrics.append(full_record)

            # --- B. Populate Table ---

            # Col 0: ID (Hidden)
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(i)))

            # Col 1: Class (Editable Dropdown)
            combo = QtWidgets.QComboBox()
            combo.addItems(MICROPLASTIC_TYPES)

            # Select the AI-predicted label
            current_label = full_record["label"]
            index = combo.findText(current_label, QtCore.Qt.MatchFlag.MatchFixedString)
            if index >= 0:
                combo.setCurrentIndex(index)

            # Connect signal to handle edits
            # We use lambda r=i to capture the current row index
            combo.currentTextChanged.connect(
                lambda text, r=i: self._on_class_changed(r, text)
            )
            self.table.setCellWidget(i, 1, combo)

            # Col 2: Confidence
            self.table.setItem(
                i, 2, QtWidgets.QTableWidgetItem(f"{p.get('score', 0):.2f}")
            )

            # Col 3: Color
            self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(color_name))

            # Cols 4-9: Morphometrics (Expanded List)
            metrics = ["area", "perimeter", "major", "minor", "deq", "skeleton"]

            for col_offset, key in enumerate(metrics):
                val = stats.get(key, 0)
                item = QtWidgets.QTableWidgetItem(f"{val:.2f}")
                item.setTextAlignment(
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(i, 4 + col_offset, item)

            # Note: Verification column removed — verification status is kept
            # in the internal `_cached_morphometrics` but not shown as a table column.

        self.table.setSortingEnabled(True)

    def _on_class_changed(self, row, new_text):
        """
        Triggered when the user changes a value in the dropdown.
        Updates the internal cache and visual status.
        """
        # Update Internal Data Cache (and keep verification flag)
        if 0 <= row < len(self._cached_morphometrics):
            self._cached_morphometrics[row]["label"] = new_text
            self._cached_morphometrics[row]["verification"] = "human_verified"

            # Optionally, visually mark the row (background) to indicate user edit
            try:
                for c in range(self.table.columnCount()):
                    it = self.table.item(row, c)
                    if it is not None:
                        it.setBackground(QtGui.QBrush(QtGui.QColor("#f0fff0")))
            except Exception:
                pass

    def delete_selected_row(self):
        """
        Removes the selected particle from the list (False Positive).
        """
        current_row = self.table.currentRow()
        if current_row < 0:
            return

        try:
            # Remove from internal cache
            self._cached_morphometrics.pop(current_row)

            # Remove from UI
            self.table.removeRow(current_row)

            # Clear preview to avoid confusion
            if self._preview_ctrl:
                self._preview_ctrl.scene.clear()

        except Exception as e:
            print(f"Error deleting row: {e}")

    def emit_save_data(self):
        """
        Sends the verified data to the main application/Directus.
        """
        # Ensure any edits made directly in the table are reflected in the cached records
        try:
            self._sync_table_to_cache()
        except Exception:
            pass

        print(f"Updating {len(self._cached_morphometrics)} records...")
        self.data_committed.emit(self._cached_morphometrics)
        self.close()

    def _sync_table_to_cache(self):
        """Read current table widgets/items and update the internal `_cached_morphometrics`.

        This ensures any user edits in the table (dropdowns, numeric edits) are captured
        before sending data to Directus.
        """
        if not self.table or not self._cached_morphometrics:
            return

        row_count = self.table.rowCount()
        for r in range(min(row_count, len(self._cached_morphometrics))):
            rec = self._cached_morphometrics[r]

            # Class: cell widget combo
            try:
                widget = self.table.cellWidget(r, 1)
                if isinstance(widget, QtWidgets.QComboBox):
                    rec["label"] = widget.currentText()
            except Exception:
                pass

            # Confidence
            try:
                item = self.table.item(r, 2)
                if item is not None:
                    rec["score"] = float(item.text())
            except Exception:
                pass

            # Color
            try:
                item = self.table.item(r, 3)
                if item is not None:
                    rec["color_name"] = item.text()
            except Exception:
                pass

            # Morphometrics: cols 4-9
            metrics = ["area", "perimeter", "major", "minor", "deq", "skeleton"]
            for i, key in enumerate(metrics):
                try:
                    item = self.table.item(r, 4 + i)
                    if item is not None:
                        rec[key] = float(item.text())
                except Exception:
                    pass

            # Verification remains in the internal cache but is not a table column
            # (we preserve any existing value)

    def _on_selection_changed(self):
        """
        Crops the image to the selected particle for the preview window.
        """
        items = self.table.selectedItems()
        if not items:
            return

        row = items[0].row()

        # Safety check
        if row >= len(self._cached_morphometrics):
            return

        pred = self._cached_morphometrics[row]
        pts = pred.get("points", [])
        bbox = pred.get("bbox", [])

        if not pts and not bbox:
            return

        try:
            # Determine Crop Coordinates
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                x0, y0 = int(min(xs)), int(min(ys))
                x1, y1 = int(max(xs)), int(max(ys))
            else:
                x0, y0, w, h = [int(v) for v in bbox]
                x1, y1 = x0 + w, y0 + h

            # Add Padding for context
            pad = 30
            x0 = max(0, x0 - pad)
            y0 = max(0, y0 - pad)
            x1 = min(self._last_pixmap.width(), x1 + pad)
            y1 = min(self._last_pixmap.height(), y1 + pad)

            # Crop
            rect = QtCore.QRect(x0, y0, x1 - x0, y1 - y0)
            cropped = self._last_pixmap.copy(rect)

            # Display
            if self._preview_ctrl:
                self._preview_ctrl.setPixmap(cropped)

        except Exception:
            pass
