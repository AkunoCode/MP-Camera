from PyQt6 import QtWidgets, QtCore, QtGui
import json
import datetime
import traceback
import re
from threading import Thread
from typing import Optional, Dict, List, Any, Union

# --- Safe Service Imports ---
try:
    from mpcamera.services.directus import DirectusClient
except ImportError:
    DirectusClient = None


class WorkerSignals(QtCore.QObject):
    """Signals for background API tasks."""

    success = QtCore.pyqtSignal(str, object)  # action, response
    error = QtCore.pyqtSignal(str)


class SamplePageController(QtCore.QObject):
    """
    Controller to manage the Samples Page UI, including Table population,
    Search, and CRUD operations.
    """

    def __init__(
        self, sample_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow
    ):
        super().__init__()
        self.page = sample_page
        self.main_window = main_window
        self.signals = WorkerSignals()

        # 1. Locate Widgets
        self.ui = self._find_ui_elements()

        # 2. Init UI State
        self._init_table_behavior()
        self._setup_connections()

        # Set default date to today
        if self.ui["date_edit"]:
            self.ui["date_edit"].setDate(QtCore.QDate.currentDate())

        # 3. Initial Load
        self.populate_table()

        # 4. Listen for global refreshes
        if hasattr(self.main_window, "dataLoaded"):
            self.main_window.dataLoaded.connect(self.populate_table)

    def _find_ui_elements(self) -> Dict[str, Any]:
        """Locate and cache UI widgets."""
        ui = {
            "table": self.page.findChild(QtWidgets.QTableWidget, "samplesTable"),
            "search_input": self.page.findChild(QtWidgets.QLineEdit, "farmNameSearch"),
            "farm_combo": self.page.findChild(QtWidgets.QComboBox, "farmNameCombo"),
            "date_edit": self.page.findChild(QtWidgets.QDateEdit, "dateCollected"),
            "create_btn": self.page.findChild(QtWidgets.QPushButton, "createRecord"),
            "update_btn": self.page.findChild(QtWidgets.QPushButton, "updateRecord"),
        }

        missing = [k for k, v in ui.items() if v is None]
        if missing:
            print(f"SamplePageController Warning: Missing widgets: {missing}")
        return ui

    def _init_table_behavior(self):
        table = self.ui["table"]
        if not table:
            return
        table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )

    def _setup_connections(self):
        """Wire signals to slots."""
        # Table
        if self.ui["table"]:
            self.ui["table"].selectionModel().selectionChanged.connect(
                self._on_selection_changed
            )

        # Search
        if self.ui["search_input"]:
            self.ui["search_input"].textChanged.connect(self._on_search_changed)

        # Buttons
        if self.ui["create_btn"]:
            self.ui["create_btn"].clicked.connect(
                lambda: self._save_record(mode="create")
            )
        if self.ui["update_btn"]:
            self.ui["update_btn"].clicked.connect(
                lambda: self._save_record(mode="update")
            )

        # Signals
        self.signals.success.connect(self._on_worker_success)
        self.signals.error.connect(self._on_worker_error)

    # ================= DATA LOADING =================

    def _fetch_sites_map(self) -> Dict[int, Dict]:
        """Returns a dictionary mapping ID -> Site Object."""
        if not self.main_window or not hasattr(self.main_window, "get_sites"):
            return {}

        raw = self.main_window.get_sites() or []
        data = (
            raw.get("data", [])
            if isinstance(raw, dict)
            else (raw if isinstance(raw, list) else [])
        )

        mapping = {}
        for s in data:
            sid = s.get("id") or s.get("site_id")
            if sid:
                mapping[sid] = s
        return mapping

    def populate_table(self):
        """Main logic to fill table and combo box."""
        table = self.ui["table"]
        if not table:
            return

        # 1. Fetch Data
        raw_samples = []
        if self.main_window and hasattr(self.main_window, "get_soilsamples"):
            r = self.main_window.get_soilsamples() or []
            raw_samples = (
                r.get("data", [])
                if isinstance(r, dict)
                else (r if isinstance(r, list) else [])
            )

        site_map = self._fetch_sites_map()

        # 2. Populate Farm Combo (lookup list)
        self._populate_farm_combo(site_map)

        # 3. Populate Table
        table.setSortingEnabled(False)
        table.setRowCount(0)

        for s in raw_samples:
            row = table.rowCount()
            table.insertRow(row)

            # Resolve Farm Name
            farm_name = self._resolve_farm_name(s, site_map)

            # Resolve Date
            date_val = (
                s.get("date_collected")
                or s.get("dateCollected")
                or s.get("collected")
                or ""
            )

            # Create Items
            item_farm = QtWidgets.QTableWidgetItem(str(farm_name))
            item_farm.setData(
                QtCore.Qt.ItemDataRole.UserRole, json.dumps(s, default=str)
            )

            item_date = QtWidgets.QTableWidgetItem(str(date_val))

            table.setItem(row, 0, item_farm)
            table.setItem(row, 1, item_date)

        table.resizeColumnsToContents()
        table.setSortingEnabled(True)

        # Re-apply search if exists
        if self.ui["search_input"]:
            self._on_search_changed(self.ui["search_input"].text())

    def _populate_farm_combo(self, site_map):
        combo = self.ui["farm_combo"]
        if not combo:
            return

        combo.blockSignals(True)
        combo.clear()
        combo.addItem("", None)  # Empty default

        # Sort by name
        sorted_sites = sorted(
            site_map.items(),
            key=lambda x: str(x[1].get("site_name") or x[1].get("name") or "").lower(),
        )

        for sid, s in sorted_sites:
            display = s.get("site_name") or s.get("name") or str(sid)
            combo.addItem(str(display), sid)

        combo.blockSignals(False)

    def _resolve_farm_name(self, sample, site_map):
        """Helper to find the farm name from a sample object."""
        # 1. Check nested object
        site_field = sample.get("site")
        if isinstance(site_field, dict):
            return site_field.get("site_name") or site_field.get("name") or ""

        # 2. Check ID in map
        if site_field in site_map:
            site_obj = site_map[site_field]
            return site_obj.get("site_name") or site_obj.get("name") or ""

        # 3. Fallback to flat fields
        return (
            sample.get("site_name")
            or sample.get("siteName")
            or sample.get("site_label")
            or ""
        )

    def _on_search_changed(self, text):
        """Filter table rows."""
        table = self.ui["table"]
        if not table:
            return

        query = (text or "").strip().lower()

        for r in range(table.rowCount()):
            item = table.item(r, 0)  # Farm Name column
            if not item:
                continue

            val = item.text().lower()
            table.setRowHidden(r, query not in val)

    # ================= FORM & SELECTION =================

    def _on_selection_changed(self):
        table = self.ui["table"]
        if not table:
            return

        rows = table.selectionModel().selectedRows()

        if rows:
            # Row Selected: Load Data
            idx = rows[0].row()
            item = table.item(idx, 0)
            if item:
                try:
                    data = json.loads(item.data(QtCore.Qt.ItemDataRole.UserRole))
                    self._fill_form(data)
                    self._toggle_buttons(mode="edit")
                except Exception:
                    self._reset_form()
        else:
            # No Selection: Reset
            self._reset_form()
            self._toggle_buttons(mode="create")

    def _fill_form(self, data):
        """Populate UI from sample data."""
        # 1. Set Farm Combo
        combo = self.ui["farm_combo"]
        if combo:
            site_field = data.get("site")
            sid = None

            if isinstance(site_field, dict):
                sid = site_field.get("id") or site_field.get("site_id")
            else:
                try:
                    sid = int(site_field)
                except (ValueError, TypeError):
                    sid = site_field  # Could be UUID string

            idx = combo.findData(sid)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentIndex(0)

        # 2. Set Date
        date_edit = self.ui["date_edit"]
        if date_edit:
            raw_date = (
                data.get("date_collected")
                or data.get("dateCollected")
                or data.get("collected")
            )
            qdate = self._parse_date_string(raw_date)
            if qdate.isValid():
                date_edit.setDate(qdate)
            else:
                date_edit.setDate(QtCore.QDate.currentDate())

    def _reset_form(self):
        if self.ui["farm_combo"]:
            self.ui["farm_combo"].setCurrentIndex(0)
        if self.ui["date_edit"]:
            self.ui["date_edit"].setDate(QtCore.QDate.currentDate())

    def _parse_date_string(self, s: Any) -> QtCore.QDate:
        """Robust date parsing logic."""
        if not s:
            return QtCore.QDate()

        # Already a date object?
        if isinstance(s, (datetime.date, datetime.datetime)):
            return QtCore.QDate(s.year, s.month, s.day)

        s_str = str(s).strip()

        # Remove Time/Timezone info for pure date parsing
        if "T" in s_str:
            s_str = s_str.split("T")[0]
        if s_str.endswith("Z"):
            s_str = s_str[:-1]

        # Try standard Regex patterns
        # ISO (YYYY-MM-DD)
        m_iso = re.search(r"(\d{4}-\d{2}-\d{2})", s_str)
        if m_iso:
            try:
                dt = datetime.datetime.strptime(m_iso.group(1), "%Y-%m-%d")
                return QtCore.QDate(dt.year, dt.month, dt.day)
            except:
                pass

        # EU (DD-MM-YYYY)
        m_eu = re.search(r"(\d{2}-\d{2}-\d{4})", s_str)
        if m_eu:
            try:
                dt = datetime.datetime.strptime(m_eu.group(1), "%d-%m-%Y")
                return QtCore.QDate(dt.year, dt.month, dt.day)
            except:
                pass

        # Try Qt's built-in parsing
        qd = QtCore.QDate.fromString(s_str, QtCore.Qt.DateFormat.ISODate)
        if qd.isValid():
            return qd

        return QtCore.QDate()

    # ================= CRUD OPERATIONS =================

    def _save_record(self, mode="create"):
        """Unified logic for Create and Update."""
        if not DirectusClient:
            QtWidgets.QMessageBox.warning(
                self.page, "Error", "Directus client unavailable."
            )
            return

        # 1. Handle 'Unselect' behavior for Create button
        if (
            mode == "create"
            and self.ui["table"]
            and self.ui["table"].selectionModel().hasSelection()
        ):
            self.ui["table"].clearSelection()
            self._reset_form()
            return

        # 2. Collect Data
        site_id = self.ui["farm_combo"].currentData() if self.ui["farm_combo"] else None
        date_val = ""
        if self.ui["date_edit"]:
            date_val = self.ui["date_edit"].date().toString("yyyy-MM-dd")

        payload = {"site": site_id, "date_collected": date_val}

        # 3. Validate
        missing = []
        if not site_id:
            missing.append("Farm")
        if not date_val:
            missing.append("Date")

        if missing:
            QtWidgets.QMessageBox.warning(
                self.page, "Validation", f"Missing: {', '.join(missing)}"
            )
            return

        # 4. Determine ID for Update
        sample_id = None
        if mode == "update":
            rows = self.ui["table"].selectionModel().selectedRows()
            if not rows:
                return
            try:
                raw = json.loads(
                    self.ui["table"]
                    .item(rows[0].row(), 0)
                    .data(QtCore.Qt.ItemDataRole.UserRole)
                )
                sample_id = raw.get("id") or raw.get("sample_id")
            except:
                pass

            if not sample_id:
                QtWidgets.QMessageBox.warning(
                    self.page, "Error", "Cannot find Sample ID."
                )
                return

        # 5. UI Feedback & Worker
        if mode == "create":
            self.ui["create_btn"].setEnabled(False)
        if mode == "update":
            self.ui["update_btn"].setEnabled(False)

        def worker():
            try:
                from mpcamera.config import get_settings
                cfg = get_settings()
                api_url = cfg.get("services", {}).get("directus", {}).get("api_url", "").strip()
                bearer_token = cfg.get("services", {}).get("directus", {}).get("bearer_token", "").strip()
                client = DirectusClient(api_url=api_url or None, bearer_token=bearer_token or None)
                if mode == "create":
                    resp = client.create_soilsample(payload)
                    self.signals.success.emit("create", resp)
                else:
                    resp = client.update_soilsample(sample_id, payload)
                    self.signals.success.emit("update", resp)
            except Exception:
                self.signals.error.emit(traceback.format_exc())

        Thread(target=worker, daemon=True).start()

    def _on_worker_success(self, action, resp):
        msg = "Sample created." if action == "create" else "Sample updated."
        QtWidgets.QMessageBox.information(self.page, "Success", msg)

        self._reset_form()
        if self.ui["table"]:
            self.ui["table"].clearSelection()
        self._toggle_buttons(mode="create")

        # Trigger Refresh
        if self.main_window and hasattr(self.main_window, "_start_directus_fetch"):
            self.main_window._start_directus_fetch()

    def _on_worker_error(self, tb):
        print(f"Worker Error: {tb}")
        QtWidgets.QMessageBox.critical(self.page, "Error", "Operation failed.")
        self._toggle_buttons(mode="reset")

    def _toggle_buttons(self, mode):
        c_btn = self.ui["create_btn"]
        u_btn = self.ui["update_btn"]
        if not c_btn or not u_btn:
            return

        c_btn.setEnabled(True)

        if mode == "edit":
            c_btn.setText("Unselect Item")
            u_btn.setEnabled(True)
            u_btn.setStyleSheet("")
        elif mode == "create":
            c_btn.setText("Create New Record")
            u_btn.setEnabled(False)
            u_btn.setStyleSheet("background-color:#ddd;color:#666;")
        elif mode == "reset":
            u_btn.setEnabled(True)


# ================= ENTRY POINT =================


def setup(sample_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    """Entry point called by main application."""
    try:
        sample_page._controller = SamplePageController(sample_page, main_window)
    except Exception as e:
        print(f"SamplePage setup failed: {e}")
        traceback.print_exc()
