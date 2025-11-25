from PyQt6 import QtWidgets, QtCore
from mpcamera.utils.results_manager import ResultsManager
from mpcamera.utils.color_utils import get_color_name


class ResultsWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inference Results (Large)")
        self.resize(1100, 700)

        # Create Layout
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # Create Table
        self.table = QtWidgets.QTableWidget()
        headers = [
            "Label",
            "Score",
            "Color",
            "Area (μm²)",
            "Perimeter (μm)",
            "Major (μm)",
            "Minor (μm)",
            "Deq (μm)",
            "Skeleton (μm)",
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )

        # Make the table expand to fill the window width/height
        try:
            self.table.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
        except Exception:
            pass

        # Set header resize mode so columns stretch to fill available width
        try:
            header = self.table.horizontalHeader()
            for i in range(self.table.columnCount()):
                try:
                    header.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeMode.Stretch)
                except Exception:
                    # Fallback: set global mode if per-section API not available
                    try:
                        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
                    except Exception:
                        pass
        except Exception:
            pass

        # Reduce outer margins so the table can use full width
        try:
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        except Exception:
            pass

        layout.addWidget(self.table)

    def update_data(self, preds, last_pixmap, current_frame_np):
        """Populates the table with prediction data."""
        if not preds or not last_pixmap:
            self.table.setRowCount(0)
            return

        self.table.setRowCount(0)
        w = last_pixmap.width()
        h = last_pixmap.height()

        # Access calculation logic via the existing Manager
        # Note: This requires importing ResultsManager inside this file

        for p in preds:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Calculate
            stats = ResultsManager.calculate_morphometrics(p, w, h, magnification=1.0)

            # Color
            color_name = ""
            if current_frame_np is not None:
                try:
                    pts = p.get("points", [])
                    if pts:
                        color_name = get_color_name(current_frame_np, pts)
                except:
                    pass

            # Helpers
            def set_item(col, text):
                self.table.setItem(row, col, QtWidgets.QTableWidgetItem(str(text)))

            set_item(0, p.get("label", ""))
            set_item(1, f"{p.get('score', 0):.2f}")
            set_item(2, color_name)

            # Metrics
            metrics = ["area", "perimeter", "major", "minor", "deq", "skeleton"]
            for i, key in enumerate(metrics):
                val = stats.get(key)
                text = f"{val:.2f}" if val is not None else ""
                set_item(3 + i, text)
