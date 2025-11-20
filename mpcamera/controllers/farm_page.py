from PyQt6 import QtWidgets, QtCore, QtGui
import json
import traceback
from threading import Thread
from typing import Optional, Dict, List, Any

# --- Safe Service Imports ---
try:
    from mpcamera.services.directus import DirectusClient
except ImportError:
    DirectusClient = None


class WorkerSignals(QtCore.QObject):
    """Signals for background API tasks."""

    success = QtCore.pyqtSignal(str, object)  # action_type, response_data
    error = QtCore.pyqtSignal(str)


class FarmPageController(QtCore.QObject):
    """
    Controller to manage the Farm Page UI, including the Table (List)
    and the Form (Create/Update).
    """

    def __init__(
        self, farm_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow
    ):
        super().__init__()
        self.page = farm_page
        self.main_window = main_window
        self.signals = WorkerSignals()

        # 1. Locate Widgets
        self.ui = self._find_ui_elements()

        # 2. Init UI State
        self._init_table_behavior()
        self._setup_connections()

        # 3. Initial Data Load
        self.populate_table()

        # 4. Listen for global refreshes
        if hasattr(self.main_window, "dataLoaded"):
            self.main_window.dataLoaded.connect(self.populate_table)

    def _find_ui_elements(self) -> Dict[str, Any]:
        """Locate and cache all UI widgets."""
        ui = {
            # Search / Table
            "table": self.page.findChild(QtWidgets.QTableWidget, "farmsTable"),
            "search_input": self.page.findChild(QtWidgets.QLineEdit, "farmNameSearch"),
            "practice_filter": self.page.findChild(
                QtWidgets.QComboBox, "practiceComboSearch"
            ),
            # Form Inputs
            "farm_name": self.page.findChild(QtWidgets.QLineEdit, "farmNameInput"),
            "owner_name": self.page.findChild(QtWidgets.QLineEdit, "ownerNameInput"),
            "address": self.page.findChild(QtWidgets.QLineEdit, "addressInput"),
            "long_spin": self.page.findChild(QtWidgets.QDoubleSpinBox, "longInput"),
            "lat_spin": self.page.findChild(QtWidgets.QDoubleSpinBox, "latInput"),
            "land_area": self.page.findChild(QtWidgets.QDoubleSpinBox, "landAreaInput"),
            "water_group": self.page.findChild(QtWidgets.QGroupBox, "waterSourceGroup"),
            "plastic_group": self.page.findChild(
                QtWidgets.QGroupBox, "plasticActGroup"
            ),
            "soil_combo": self.page.findChild(QtWidgets.QComboBox, "soilTextureCombo"),
            "crops_input": self.page.findChild(QtWidgets.QLineEdit, "cropsInput"),
            "practice_combo": self.page.findChild(QtWidgets.QComboBox, "practiceCombo"),
            "remarks": self.page.findChild(QtWidgets.QTextEdit, "remarksText"),
            # Actions
            "create_btn": self.page.findChild(QtWidgets.QPushButton, "createRecord"),
            "update_btn": self.page.findChild(QtWidgets.QPushButton, "updateRecord"),
        }

        # Log missing important widgets
        missing = [k for k, v in ui.items() if v is None]
        if missing:
            print(f"FarmPageController Warning: Missing widgets: {missing}")

        return ui

    def _init_table_behavior(self):
        """Configure table selection and headers."""
        table = self.ui["table"]
        if not table:
            return

        table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        table.setColumnCount(max(3, table.columnCount()))
        table.setHorizontalHeaderLabels(["Practice", "Farm Name", "Address"])
        table.horizontalHeader().setStretchLastSection(True)

    def _setup_connections(self):
        """Wire signals."""
        # Table Selection
        if self.ui["table"]:
            self.ui["table"].selectionModel().selectionChanged.connect(
                self._on_selection_changed
            )

        # Search Filters
        if self.ui["search_input"]:
            self.ui["search_input"].textChanged.connect(self._apply_filters)
        if self.ui["practice_filter"]:
            self.ui["practice_filter"].currentTextChanged.connect(self._apply_filters)

        # CRUD Buttons
        if self.ui["create_btn"]:
            self.ui["create_btn"].clicked.connect(
                lambda: self._save_record(mode="create")
            )
        if self.ui["update_btn"]:
            self.ui["update_btn"].clicked.connect(
                lambda: self._save_record(mode="update")
            )

        # Worker Signals
        self.signals.success.connect(self._on_worker_success)
        self.signals.error.connect(self._on_worker_error)

    # ================= DATA & TABLE LOGIC =================

    def populate_table(self):
        """Fetch sites and render table."""
        table = self.ui["table"]
        if not table:
            return

        # Fetch data safely
        sites = []
        if self.main_window and hasattr(self.main_window, "get_sites"):
            raw = self.main_window.get_sites() or []
            sites = (
                raw.get("data", [])
                if isinstance(raw, dict)
                else (raw if isinstance(raw, list) else [])
            )

        table.setSortingEnabled(False)
        table.setRowCount(0)

        practices_found = set()

        for s in sites:
            row = table.rowCount()
            table.insertRow(row)

            # Extract Data
            practice = self._get_str(
                s, ["cultivation_practice", "practice", "farm_practice"]
            )
            name = self._get_str(s, ["site_name", "name", "title"])
            addr = self._get_str(s, ["address", "location"])

            if practice:
                practices_found.add(practice)

            # Create Items
            item_prac = QtWidgets.QTableWidgetItem(practice)
            item_name = QtWidgets.QTableWidgetItem(name)
            item_addr = QtWidgets.QTableWidgetItem(addr)

            # Store full object in the Name column
            item_name.setData(
                QtCore.Qt.ItemDataRole.UserRole, json.dumps(s, default=str)
            )

            table.setItem(row, 0, item_prac)
            table.setItem(row, 1, item_name)
            table.setItem(row, 2, item_addr)

        table.resizeColumnsToContents()
        table.setSortingEnabled(True)

        self._update_combos(practices_found)
        self._apply_filters()  # Re-apply any existing search terms

    def _update_combos(self, practices: set):
        """Update both the form combo and the search filter combo."""
        sorted_practices = sorted(list(practices))

        # Update Form Combo
        cb = self.ui["practice_combo"]
        if cb:
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("")
            cb.addItems(sorted_practices)
            cb.blockSignals(False)

        # Update Filter Combo
        cb_search = self.ui["practice_filter"]
        if cb_search:
            current = cb_search.currentText()
            cb_search.blockSignals(True)
            cb_search.clear()
            cb_search.addItem("")  # All
            cb_search.addItems(sorted_practices)
            cb_search.setCurrentText(current)  # Restore selection
            cb_search.blockSignals(False)

    def _apply_filters(self):
        """Filter table rows based on Search Input and Practice Combo."""
        table = self.ui["table"]
        if not table:
            return

        txt_name = (
            self.ui["search_input"].text().lower().strip()
            if self.ui["search_input"]
            else ""
        )
        txt_prac = (
            self.ui["practice_filter"].currentText().lower().strip()
            if self.ui["practice_filter"]
            else ""
        )

        for r in range(table.rowCount()):
            # Col 1 is Name, Col 0 is Practice
            it_prac = table.item(r, 0)
            it_name = table.item(r, 1)

            val_prac = it_prac.text().lower() if it_prac else ""
            val_name = it_name.text().lower() if it_name else ""

            match_name = txt_name in val_name
            match_prac = txt_prac in val_prac if txt_prac else True

            table.setRowHidden(r, not (match_name and match_prac))

    # ================= FORM LOGIC =================

    def _on_selection_changed(self):
        """Handle row selection: fill form and toggle buttons."""
        table = self.ui["table"]
        if not table:
            return

        selected_rows = table.selectionModel().selectedRows()

        if selected_rows:
            # Row Selected: Load Data
            idx = selected_rows[0].row()
            item = table.item(idx, 1)
            if item:
                try:
                    data = json.loads(item.data(QtCore.Qt.ItemDataRole.UserRole))
                    self._fill_form(data)
                    self._toggle_buttons(mode="edit")
                except Exception:
                    self._fill_form({})
        else:
            # No Selection: Clear Data
            self._fill_form({})
            self._toggle_buttons(mode="create")

    def _fill_form(self, data: Dict):
        """Populate form widgets from data dictionary."""
        if not data:
            data = {}
        u = self.ui

        # Text Fields
        if u["farm_name"]:
            u["farm_name"].setText(self._get_str(data, ["site_name", "name", "title"]))
        if u["owner_name"]:
            u["owner_name"].setText(self._get_str(data, ["owner", "contact"]))
        if u["address"]:
            u["address"].setText(self._get_str(data, ["address", "location"]))

        # Spin Boxes
        self._set_spin(u["long_spin"], data, ["longitude", "lon", "lng"])
        self._set_spin(u["lat_spin"], data, ["latitude", "lat"])
        self._set_spin(u["land_area"], data, ["area_ha", "land_area"])

        # Combos
        self._set_combo(
            u["soil_combo"], self._get_str(data, ["soil_type", "soil_texture"])
        )
        self._set_combo(
            u["practice_combo"],
            self._get_str(data, ["cultivation_practice", "practice"]),
        )

        # Crops (List to comma-string)
        crops = data.get("crops", "")
        if isinstance(crops, list):
            crops = ", ".join([str(c) for c in crops])
        if u["crops_input"]:
            u["crops_input"].setText(str(crops))

        # Checkbox Groups
        self._set_checkbox_group(u["water_group"], data, ["water_source", "water"])
        self._set_checkbox_group(
            u["plastic_group"], data, ["plastic_activity", "plastic_activities"]
        )

        # Remarks
        if u["remarks"]:
            u["remarks"].setPlainText(self._get_str(data, ["remarks", "notes"]))

    def _collect_form_data(self) -> Dict:
        """Scrape data from UI widgets into a dictionary."""
        u = self.ui

        data = {
            "site_name": u["farm_name"].text().strip() if u["farm_name"] else "",
            "owner": u["owner_name"].text().strip() if u["owner_name"] else "",
            "address": u["address"].text().strip() if u["address"] else "",
            "longitude": u["long_spin"].value() if u["long_spin"] else 0.0,
            "latitude": u["lat_spin"].value() if u["lat_spin"] else 0.0,
            "land_area_ha": u["land_area"].value() if u["land_area"] else 0.0,
            "soil_type": u["soil_combo"].currentText() if u["soil_combo"] else "",
            "cultivation_practice": (
                u["practice_combo"].currentText() if u["practice_combo"] else ""
            ),
            "remarks": u["remarks"].toPlainText() if u["remarks"] else "",
        }

        # Crops
        if u["crops_input"]:
            raw = u["crops_input"].text()
            data["crops"] = [x.strip() for x in raw.split(",") if x.strip()]
        else:
            data["crops"] = []

        # Checkboxes
        data["water_source"] = self._get_checked_labels(u["water_group"])
        data["plastic_activity"] = self._get_checked_labels(u["plastic_group"])

        return data

    # ================= ACTION LOGIC =================

    def _save_record(self, mode="create"):
        """Handle Create or Update logic."""
        if not DirectusClient:
            QtWidgets.QMessageBox.warning(
                self.page, "Error", "Directus client unavailable."
            )
            return

        # 1. Unselect logic for 'Create' button acting as 'Clear'
        if (
            mode == "create"
            and self.ui["table"]
            and self.ui["table"].selectionModel().hasSelection()
        ):
            self.ui["table"].clearSelection()
            self._fill_form({})
            return

        # 2. Validate
        payload = self._collect_form_data()
        missing = []
        if not payload["site_name"]:
            missing.append("Farm Name")
        if payload["longitude"] == 0:
            missing.append("Longitude")
        if payload["latitude"] == 0:
            missing.append("Latitude")

        if missing:
            QtWidgets.QMessageBox.warning(
                self.page, "Validation", f"Missing: {', '.join(missing)}"
            )
            return

        # 3. Identify ID for Update
        site_id = None
        if mode == "update":
            # Extract ID from currently selected row
            if not self.ui["table"]:
                return
            rows = self.ui["table"].selectionModel().selectedRows()
            if not rows:
                return

            try:
                raw_json = (
                    self.ui["table"]
                    .item(rows[0].row(), 1)
                    .data(QtCore.Qt.ItemDataRole.UserRole)
                )
                obj = json.loads(raw_json)
                site_id = obj.get("id")
            except Exception:
                pass

            if not site_id:
                QtWidgets.QMessageBox.warning(
                    self.page, "Error", "Could not determine Site ID for update."
                )
                return

        # 4. UI Feedback
        if mode == "create":
            self.ui["create_btn"].setEnabled(False)
        if mode == "update":
            self.ui["update_btn"].setEnabled(False)

        # 5. Threading
        def worker():
            try:
                client = DirectusClient()
                if mode == "create":
                    resp = client.create_site(payload)
                    self.signals.success.emit("create", resp)
                else:
                    resp = client.update_site(site_id, payload)
                    self.signals.success.emit("update", resp)
            except Exception:
                self.signals.error.emit(traceback.format_exc())

        Thread(target=worker, daemon=True).start()

    def _on_worker_success(self, action, resp):
        """Handle successful API response."""
        msg = (
            "Site created successfully."
            if action == "create"
            else "Site updated successfully."
        )
        QtWidgets.QMessageBox.information(self.page, "Success", msg)

        # Reset UI
        self._fill_form({})
        if self.ui["table"]:
            self.ui["table"].clearSelection()
        self._toggle_buttons(mode="create")

        # Trigger Refresh
        if self.main_window and hasattr(self.main_window, "_start_directus_fetch"):
            self.main_window._start_directus_fetch()

    def _on_worker_error(self, tb):
        print(f"Worker Error: {tb}")
        QtWidgets.QMessageBox.critical(
            self.page, "Failed", "Operation failed. Check console."
        )
        self._toggle_buttons(mode="reset")  # Re-enable buttons

    # ================= HELPERS =================

    def _toggle_buttons(self, mode):
        """Manage button states."""
        c_btn = self.ui["create_btn"]
        u_btn = self.ui["update_btn"]

        if not c_btn or not u_btn:
            return

        c_btn.setEnabled(True)

        if mode == "edit":
            c_btn.setText("Unselect Item")
            u_btn.setEnabled(True)
            u_btn.setStyleSheet("")  # Reset style
        elif mode == "create":
            c_btn.setText("Create New Record")
            u_btn.setEnabled(False)
            u_btn.setStyleSheet("background-color:#ddd;color:#666;")
        elif mode == "reset":
            c_btn.setEnabled(True)
            u_btn.setEnabled(True)

    def _get_str(self, data, keys):
        """Return first non-empty value from a list of keys."""
        if not data:
            return ""
        for k in keys:
            val = data.get(k)
            if val:
                return str(val)
        return ""

    def _set_spin(self, widget, data, keys):
        if not widget:
            return
        for k in keys:
            val = data.get(k)
            if val is not None:
                try:
                    widget.setValue(float(val))
                    return
                except:
                    pass
        widget.setValue(0.0)

    def _set_combo(self, widget, value):
        if not widget or not value:
            if widget:
                widget.setCurrentIndex(-1)
            return

        # Flexible matching
        val_lower = str(value).lower()
        for i in range(widget.count()):
            if val_lower in widget.itemText(i).lower():
                widget.setCurrentIndex(i)
                return

        # Allow setting text if editable
        if widget.isEditable():
            widget.setEditText(str(value))

    def _set_checkbox_group(self, group, data, keys):
        if not group:
            return

        # 1. Find the list of values
        target_values = []
        for k in keys:
            v = data.get(k)
            if v:
                if isinstance(v, list):
                    target_values = [str(x).lower() for x in v]
                else:
                    target_values = [str(v).lower()]
                break

        # 2. Iterate checkboxes and check matches
        for cb in group.findChildren(QtWidgets.QCheckBox):
            cb.setChecked(False)  # Reset
            if not target_values:
                continue

            txt = (cb.text() or "").lower()
            obj = (cb.objectName() or "").lower()

            # Check if any target value is inside the checkbox label or vice versa
            if any(tv in txt or txt in tv or tv in obj for tv in target_values):
                cb.setChecked(True)

    def _get_checked_labels(self, group) -> List[str]:
        res = []
        if group:
            for cb in group.findChildren(QtWidgets.QCheckBox):
                if cb.isChecked():
                    res.append(cb.text())
        return res


# ================= ENTRY POINT =================


def setup(farm_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    """Entry point called by main application."""
    try:
        # Attach controller to widget to keep it alive
        farm_page._controller = FarmPageController(farm_page, main_window)
    except Exception as e:
        print(f"FarmPage setup failed: {e}")
        traceback.print_exc()
