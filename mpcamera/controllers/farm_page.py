from PyQt6 import QtWidgets, QtCore
import json
from threading import Thread
import traceback

try:
    from mpcamera.services.directus import DirectusClient
except Exception:
    DirectusClient = None

from PyQt6 import QtWidgets, QtCore
import json
from threading import Thread
import traceback

try:
    from mpcamera.services.directus import DirectusClient
except Exception:
    DirectusClient = None


def setup(farm_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    """Initialize the farm page UI: populate `farmsTable` from Directus sites
    and wire selection to populate the form on the right.
    """
    if farm_page is None:
        return

    # find widgets (best-effort)
    farms_table = farm_page.findChild(QtWidgets.QTableWidget, "farmsTable")
    search_input = farm_page.findChild(QtWidgets.QLineEdit, "farmNameSearch")
    practice_search_combo = farm_page.findChild(
        QtWidgets.QComboBox, "practiceComboSearch"
    )

    # form fields
    farm_name = farm_page.findChild(QtWidgets.QLineEdit, "farmNameInput")
    owner_name = farm_page.findChild(QtWidgets.QLineEdit, "ownerNameInput")
    address = farm_page.findChild(QtWidgets.QLineEdit, "addressInput")
    long_spin = farm_page.findChild(QtWidgets.QDoubleSpinBox, "longInput")
    lat_spin = farm_page.findChild(QtWidgets.QDoubleSpinBox, "latInput")
    land_area = farm_page.findChild(QtWidgets.QDoubleSpinBox, "landAreaInput")
    water_group = farm_page.findChild(QtWidgets.QGroupBox, "waterSourceGroup")
    soil_combo = farm_page.findChild(QtWidgets.QComboBox, "soilTextureCombo")
    crops_input = farm_page.findChild(QtWidgets.QLineEdit, "cropsInput")
    practice_input = farm_page.findChild(QtWidgets.QComboBox, "practiceCombo")
    remarks = farm_page.findChild(QtWidgets.QTextEdit, "remarksText")
    create_btn = farm_page.findChild(QtWidgets.QPushButton, "createRecord")
    update_btn = farm_page.findChild(QtWidgets.QPushButton, "updateRecord")

    # ensure table basic setup
    if farms_table is not None:
        farms_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        farms_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        farms_table.setColumnCount(max(3, farms_table.columnCount()))
        try:
            farms_table.setHorizontalHeaderLabels(["Practice", "Farm Name", "Address"])
        except Exception:
            pass

    def _get_sites_list():
        try:
            if main_window is None:
                return []
            sites = main_window.get_sites() or []
            if isinstance(sites, dict) and "data" in sites:
                return sites.get("data") or []
            if isinstance(sites, list):
                return sites
            return []
        except Exception:
            return []

    def populate_table():
        items = _get_sites_list()
        if farms_table is None:
            return
        farms_table.setRowCount(0)
        practices = set()
        for s in items:
            r = farms_table.rowCount()
            farms_table.insertRow(r)
            practice = (
                s.get("cultivation_practice")
                or s.get("practice")
                or s.get("farm_practice")
                or ""
            )
            practices.add(str(practice)) if practice else None
            try:
                farms_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(practice)))
            except Exception:
                pass

            name = s.get("site_name") or s.get("name") or s.get("title") or ""
            item_name = QtWidgets.QTableWidgetItem(str(name))
            try:
                item_name.setData(
                    QtCore.Qt.ItemDataRole.UserRole, json.dumps(s, default=str)
                )
            except Exception:
                try:
                    item_name.setData(QtCore.Qt.ItemDataRole.UserRole, str(s))
                except Exception:
                    pass
            try:
                farms_table.setItem(r, 1, item_name)
            except Exception:
                pass

            addr = s.get("address") or s.get("location") or ""
            try:
                farms_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(addr)))
            except Exception:
                pass

        try:
            farms_table.resizeColumnsToContents()
        except Exception:
            pass

        # update practice combo
        if practice_input is not None:
            try:
                practice_input.blockSignals(True)
                practice_input.clear()
                practice_input.addItem("")
                for p in sorted(practices):
                    practice_input.addItem(str(p))
                practice_input.blockSignals(False)
            except Exception:
                pass
        # update practice search combo (left-hand filter)
        if practice_search_combo is not None:
            try:
                practice_search_combo.blockSignals(True)
                practice_search_combo.clear()
                # empty means show all
                practice_search_combo.addItem("")
                for p in sorted(practices):
                    practice_search_combo.addItem(str(p))
                practice_search_combo.blockSignals(False)
            except Exception:
                pass

    def _fill_form_from_site(s):
        # accepts dict or JSON string; empty dict clears fields
        try:
            if isinstance(s, str):
                try:
                    s = json.loads(s)
                except Exception:
                    s = {"raw": s}
            if isinstance(s, dict) and not s:
                # clear
                for w in [farm_name, owner_name, address, crops_input]:
                    try:
                        if w is not None:
                            w.setText("")
                    except Exception:
                        pass
                for sp in [long_spin, lat_spin, land_area]:
                    try:
                        if sp is not None:
                            sp.setValue(0.0)
                    except Exception:
                        pass
                for cb in [soil_combo, practice_input]:
                    try:
                        if cb is None:
                            continue
                        try:
                            cb.setCurrentIndex(-1)
                        except Exception:
                            try:
                                if cb.isEditable():
                                    cb.setEditText("")
                                else:
                                    if cb.count() == 0 or cb.itemText(0) != "":
                                        cb.insertItem(0, "")
                                    cb.setCurrentIndex(0)
                            except Exception:
                                pass
                    except Exception:
                        pass
                try:
                    if water_group is not None:
                        for cb in water_group.findChildren(QtWidgets.QCheckBox):
                            try:
                                cb.setChecked(False)
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    pg = farm_page.findChild(QtWidgets.QGroupBox, "plasticActGroup")
                    if pg is not None:
                        for cb in pg.findChildren(QtWidgets.QCheckBox):
                            try:
                                cb.setChecked(False)
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    if remarks is not None:
                        remarks.setPlainText("")
                except Exception:
                    pass
                return

            # helpers
            def _set_line(w, v):
                try:
                    if w is None:
                        return
                    w.setText(str(v) if v is not None else "")
                except Exception:
                    pass

            def _set_spin(w, v):
                try:
                    if w is None:
                        return
                    if v is None:
                        w.setValue(0.0)
                    else:
                        try:
                            w.setValue(float(v))
                        except Exception:
                            w.setValue(0.0)
                except Exception:
                    pass

            _set_line(
                farm_name, s.get("site_name") or s.get("name") or s.get("title") or ""
            )
            _set_line(owner_name, s.get("owner") or s.get("contact") or "")
            _set_line(address, s.get("address") or s.get("location") or "")
            _set_spin(
                long_spin,
                s.get("longitude") or s.get("lon") or s.get("long") or s.get("lng"),
            )
            _set_spin(lat_spin, s.get("latitude") or s.get("lat"))
            _set_spin(
                land_area, s.get("area_ha") or s.get("land_area") or s.get("area")
            )

            # water source
            try:
                ws = s.get("water_source") or s.get("waterSources") or s.get("water")
                if ws is None:
                    ws_list = []
                elif isinstance(ws, list):
                    ws_list = [str(x).lower() for x in ws if x]
                else:
                    ws_list = [str(ws).lower()]

                def _apply_group_checks(group, values):
                    try:
                        if group is None:
                            return
                        cbs = group.findChildren(QtWidgets.QCheckBox)
                        for cb in cbs:
                            try:
                                cb.setChecked(False)
                            except Exception:
                                pass
                        for val in values:
                            if not val:
                                continue
                            for cb in cbs:
                                try:
                                    cb_text = (cb.text() or "").lower()
                                    cb_obj = (cb.objectName() or "").lower()
                                    if (
                                        val in cb_text
                                        or cb_text in val
                                        or val in cb_obj
                                    ):
                                        cb.setChecked(True)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                _apply_group_checks(water_group, ws_list)
            except Exception:
                pass

            # soil
            try:
                soil_val = s.get("soil_type") or s.get("soil_texture") or s.get("soil")
                if soil_combo is not None and soil_val is not None:
                    sval = str(soil_val).lower()
                    matched = False
                    for i in range(soil_combo.count()):
                        try:
                            it = soil_combo.itemText(i) or ""
                            if sval in it.lower() or it.lower() in sval:
                                soil_combo.setCurrentIndex(i)
                                matched = True
                                break
                        except Exception:
                            pass
                    if not matched:
                        try:
                            if soil_combo.isEditable():
                                soil_combo.setEditText(str(soil_val))
                        except Exception:
                            pass
            except Exception:
                pass

            # crops
            try:
                crops_val = s.get("crops")
                if isinstance(crops_val, list):
                    crops_input.setText(",".join(crops_val))
                else:
                    crops_input.setText(str(crops_val) if crops_val is not None else "")
            except Exception:
                pass

            # practice
            try:
                if practice_input is not None:
                    practice_val = (
                        s.get("cultivation_practice") or s.get("practice") or None
                    )
                    if practice_val is not None:
                        idx = practice_input.findText(str(practice_val))
                        if idx >= 0:
                            practice_input.setCurrentIndex(idx)
                        else:
                            try:
                                practice_input.addItem(str(practice_val))
                                practice_input.setCurrentIndex(
                                    practice_input.count() - 1
                                )
                            except Exception:
                                pass
            except Exception:
                pass

            # plastic activity
            try:
                pa = s.get("plastic_activity") or s.get("plastic_activities")
                if pa is None:
                    pa_list = []
                elif isinstance(pa, list):
                    pa_list = [str(x).lower() for x in pa if x]
                else:
                    pa_list = [str(pa).lower()]
                pg = farm_page.findChild(QtWidgets.QGroupBox, "plasticActGroup")
                try:
                    if pg is not None:
                        for cb in pg.findChildren(QtWidgets.QCheckBox):
                            try:
                                cb.setChecked(False)
                            except Exception:
                                pass
                        for val in pa_list:
                            for cb in pg.findChildren(QtWidgets.QCheckBox):
                                try:
                                    txt = (cb.text() or "").lower()
                                    obj = (cb.objectName() or "").lower()
                                    if val in txt or txt in val or val in obj:
                                        cb.setChecked(True)
                                except Exception:
                                    pass
                except Exception:
                    pass
            except Exception:
                pass

            try:
                if remarks is not None:
                    remarks.setPlainText(s.get("remarks") or s.get("notes") or "")
            except Exception:
                pass

        except Exception:
            # protect against any parse error
            try:
                print("_fill_form_from_site: failed", traceback.format_exc())
            except Exception:
                pass

    # Worker signals
    class _WorkerSignals(QtCore.QObject):
        success = QtCore.pyqtSignal(object)
        error = QtCore.pyqtSignal(str)

    signals = _WorkerSignals()

    def _handle_worker_success(resp):
        try:
            action = None
            data = None
            if isinstance(resp, (list, tuple)) and len(resp) >= 1:
                action = resp[0]
                data = resp[1] if len(resp) > 1 else None
            else:
                data = resp
        except Exception:
            data = resp
        try:
            title = "Created Site" if action != "update" else "Updated Site"
            text = (
                "Site created successfully"
                if action != "update"
                else "Site updated successfully"
            )
            QtWidgets.QMessageBox.information(farm_page, title, text)
        except Exception:
            pass
        try:
            _fill_form_from_site({})
        except Exception:
            pass
        try:
            if farms_table is not None:
                farms_table.clearSelection()
        except Exception:
            pass
        try:
            if create_btn is not None:
                create_btn.setEnabled(True)
        except Exception:
            pass
        try:
            if update_btn is not None:
                update_btn.setEnabled(False)
                update_btn.setStyleSheet("background-color:#ddd;color:#666;")
        except Exception:
            pass
        try:
            if main_window is not None and hasattr(
                main_window, "_start_directus_fetch"
            ):
                main_window._start_directus_fetch()
        except Exception:
            pass

    def _handle_worker_error(tb):
        try:
            print("_handle_worker_error:", tb[:400])
        except Exception:
            pass
        try:
            QtWidgets.QMessageBox.critical(
                farm_page, "Operation Failed", "See console for details."
            )
        except Exception:
            pass
        try:
            if create_btn is not None:
                create_btn.setEnabled(True)
        except Exception:
            pass
        try:
            if update_btn is not None:
                update_btn.setEnabled(False)
        except Exception:
            pass

    # connect signals
    try:
        signals.success.connect(_handle_worker_success)
        signals.error.connect(_handle_worker_error)
    except Exception:
        pass

    def update_create_button_label():
        try:
            if farms_table is None or create_btn is None:
                return
            sels = (
                farms_table.selectionModel().selectedRows()
                if farms_table is not None
                else []
            )
            if sels:
                create_btn.setText("Unselect Item")
                if update_btn is not None:
                    update_btn.setEnabled(True)
                    try:
                        update_btn.setStyleSheet("")
                    except Exception:
                        pass
            else:
                create_btn.setText("Create New Record")
                if update_btn is not None:
                    update_btn.setEnabled(False)
                    try:
                        update_btn.setStyleSheet("background-color:#ddd;color:#666;")
                    except Exception:
                        pass
        except Exception:
            pass

    def on_table_selection_changed():
        try:
            if farms_table is None:
                return
            sels = farms_table.selectionModel().selectedRows()
            update_create_button_label()
            if not sels:
                return
            idx = sels[0].row()
            it = farms_table.item(idx, 1)
            if it is None:
                return
            data = it.data(QtCore.Qt.ItemDataRole.UserRole)
            if data is None:
                return
            try:
                site = json.loads(data)
            except Exception:
                site = data
            _fill_form_from_site(site)
        except Exception:
            pass

    if farms_table is not None:
        try:
            farms_table.selectionModel().selectionChanged.connect(
                lambda s, d: on_table_selection_changed()
            )
            update_create_button_label()
        except Exception:
            pass

    # search
    if search_input is not None and farms_table is not None:
        try:

            def apply_filters(_=None):
                try:
                    name_txt = (
                        (search_input.text() if search_input is not None else "")
                        .strip()
                        .lower()
                    )
                except Exception:
                    name_txt = ""
                try:
                    practice_txt = (
                        (
                            practice_search_combo.currentText()
                            if practice_search_combo is not None
                            else ""
                        )
                        .strip()
                        .lower()
                    )
                except Exception:
                    practice_txt = ""

                for r in range(farms_table.rowCount()):
                    try:
                        # name match
                        item = farms_table.item(r, 1)
                        if item is None:
                            name_ok = True
                        else:
                            name = (item.text() or "").lower()
                            name_ok = (name_txt in name) if name_txt else True

                        # practice match (column 0)
                        pitem = farms_table.item(r, 0)
                        if pitem is None:
                            practice_ok = True
                        else:
                            pval = (pitem.text() or "").lower()
                            practice_ok = (
                                (practice_txt in pval) if practice_txt else True
                            )

                        farms_table.setRowHidden(r, not (name_ok and practice_ok))
                    except Exception:
                        pass

            # connect both inputs to the combined filter
            search_input.textChanged.connect(apply_filters)
            if practice_search_combo is not None:
                try:
                    practice_search_combo.currentTextChanged.connect(apply_filters)
                except Exception:
                    pass
        except Exception:
            pass

    # refresh hook
    try:
        if main_window is not None and hasattr(main_window, "dataLoaded"):
            main_window.dataLoaded.connect(populate_table)
    except Exception:
        pass

    # initial populate
    try:
        populate_table()
    except Exception:
        pass

    # Create behavior
    if create_btn is not None:

        def _on_create():
            try:
                # if selection exists -> unselect + clear
                try:
                    sels = (
                        farms_table.selectionModel().selectedRows()
                        if farms_table is not None
                        else []
                    )
                except Exception:
                    sels = []
                if sels:
                    try:
                        farms_table.clearSelection()
                        _fill_form_from_site({})
                        update_create_button_label()
                        return
                    except Exception:
                        pass

                if DirectusClient is None:
                    try:
                        QtWidgets.QMessageBox.information(
                            farm_page,
                            "Directus Not Configured",
                            "Directus client not available.",
                        )
                    except Exception:
                        pass
                    return

                # gather fields
                item = {}
                try:
                    item["site_name"] = (
                        farm_name.text() if farm_name is not None else ""
                    )
                    item["owner"] = owner_name.text() if owner_name is not None else ""
                    item["address"] = address.text() if address is not None else ""
                    item["longitude"] = (
                        str(long_spin.value()) if long_spin is not None else ""
                    )
                    item["latitude"] = (
                        str(lat_spin.value()) if lat_spin is not None else ""
                    )
                    item["land_area_ha"] = (
                        str(land_area.value()) if land_area is not None else ""
                    )
                    crops_raw = crops_input.text() if crops_input is not None else ""
                    item["crops"] = [
                        x.strip() for x in crops_raw.split(",") if x.strip()
                    ]
                    item["soil_type"] = (
                        soil_combo.currentText() if soil_combo is not None else ""
                    )
                    item["cultivation_practice"] = (
                        practice_input.currentText()
                        if practice_input is not None
                        else ""
                    )
                    ws = []
                    if water_group is not None:
                        for cb in water_group.findChildren(QtWidgets.QCheckBox):
                            try:
                                if cb.isChecked():
                                    ws.append(cb.text())
                            except Exception:
                                pass
                    item["water_source"] = ws
                    pg = farm_page.findChild(QtWidgets.QGroupBox, "plasticActGroup")
                    pa = []
                    if pg is not None:
                        for cb in pg.findChildren(QtWidgets.QCheckBox):
                            try:
                                if cb.isChecked():
                                    pa.append(cb.text())
                            except Exception:
                                pass
                    item["plastic_activity"] = pa
                    item["remarks"] = (
                        remarks.toPlainText() if remarks is not None else ""
                    )
                except Exception:
                    pass

                # validate
                missing = []
                if not item.get("site_name"):
                    missing.append("Site Name")
                try:
                    lon = float(item.get("longitude") or 0.0)
                except Exception:
                    lon = 0.0
                try:
                    lat = float(item.get("latitude") or 0.0)
                except Exception:
                    lat = 0.0
                if lon == 0.0:
                    missing.append("Longitude")
                if lat == 0.0:
                    missing.append("Latitude")
                if missing:
                    try:
                        QtWidgets.QMessageBox.warning(
                            farm_page,
                            "Validation Error",
                            "Please fill required fields: " + ", ".join(missing),
                        )
                    except Exception:
                        pass
                    return

                # disable button
                try:
                    create_btn.setEnabled(False)
                except Exception:
                    pass

                def _worker_post(itm):
                    try:
                        client = DirectusClient()
                        resp = client.create_site(itm)
                        signals.success.emit(("create", resp))
                    except Exception:
                        tb = traceback.format_exc()
                        signals.error.emit(tb)

                try:
                    t = Thread(target=_worker_post, args=(item,), daemon=True)
                    t.start()
                except Exception:
                    try:
                        _worker_post(item)
                    except Exception:
                        pass

            except Exception:
                pass

        try:
            create_btn.clicked.connect(_on_create)
        except Exception:
            pass

    # Update behavior
    if update_btn is not None:

        def _on_update():
            try:
                # require selection
                try:
                    sels = (
                        farms_table.selectionModel().selectedRows()
                        if farms_table is not None
                        else []
                    )
                except Exception:
                    sels = []
                if not sels:
                    try:
                        QtWidgets.QMessageBox.warning(
                            farm_page, "No Selection", "Please select a site to update."
                        )
                    except Exception:
                        pass
                    return
                idx = sels[0].row()
                it = farms_table.item(idx, 1)
                if it is None:
                    try:
                        QtWidgets.QMessageBox.warning(
                            farm_page, "No Data", "Selected row has no site data."
                        )
                    except Exception:
                        pass
                    return
                data = it.data(QtCore.Qt.ItemDataRole.UserRole)
                try:
                    site = json.loads(data)
                except Exception:
                    site = data
                site_id = None
                if isinstance(site, dict):
                    site_id = site.get("id") or site.get("site_id")
                if not site_id:
                    try:
                        QtWidgets.QMessageBox.warning(
                            farm_page,
                            "Missing ID",
                            "Cannot determine site id for update.",
                        )
                    except Exception:
                        pass
                    return

                # gather values similar to create
                upd = {}
                try:
                    upd["site_name"] = farm_name.text() if farm_name is not None else ""
                    upd["owner"] = owner_name.text() if owner_name is not None else ""
                    upd["address"] = address.text() if address is not None else ""
                    upd["longitude"] = (
                        str(long_spin.value()) if long_spin is not None else ""
                    )
                    upd["latitude"] = (
                        str(lat_spin.value()) if lat_spin is not None else ""
                    )
                    upd["land_area_ha"] = (
                        str(land_area.value()) if land_area is not None else ""
                    )
                    crops_raw = crops_input.text() if crops_input is not None else ""
                    upd["crops"] = [
                        x.strip() for x in crops_raw.split(",") if x.strip()
                    ]
                    upd["soil_type"] = (
                        soil_combo.currentText() if soil_combo is not None else ""
                    )
                    upd["cultivation_practice"] = (
                        practice_input.currentText()
                        if practice_input is not None
                        else ""
                    )
                    ws = []
                    if water_group is not None:
                        for cb in water_group.findChildren(QtWidgets.QCheckBox):
                            try:
                                if cb.isChecked():
                                    ws.append(cb.text())
                            except Exception:
                                pass
                    upd["water_source"] = ws
                    pg = farm_page.findChild(QtWidgets.QGroupBox, "plasticActGroup")
                    pa = []
                    if pg is not None:
                        for cb in pg.findChildren(QtWidgets.QCheckBox):
                            try:
                                if cb.isChecked():
                                    pa.append(cb.text())
                            except Exception:
                                pass
                    upd["plastic_activity"] = pa
                    upd["remarks"] = (
                        remarks.toPlainText() if remarks is not None else ""
                    )
                except Exception:
                    pass

                # validate
                missing = []
                if not upd.get("site_name"):
                    missing.append("Site Name")
                try:
                    lonv = float(upd.get("longitude") or 0.0)
                except Exception:
                    lonv = 0.0
                try:
                    latv = float(upd.get("latitude") or 0.0)
                except Exception:
                    latv = 0.0
                if lonv == 0.0:
                    missing.append("Longitude")
                if latv == 0.0:
                    missing.append("Latitude")
                if missing:
                    try:
                        QtWidgets.QMessageBox.warning(
                            farm_page,
                            "Validation Error",
                            "Please fill required fields: " + ", ".join(missing),
                        )
                    except Exception:
                        pass
                    return

                try:
                    update_btn.setEnabled(False)
                    update_btn.setStyleSheet("background-color:#ddd;color:#666;")
                except Exception:
                    pass

                def _worker_update(sid, payload):
                    try:
                        client = DirectusClient()
                        resp = client.update_site(sid, payload)
                        signals.success.emit(("update", resp))
                    except Exception:
                        tb = traceback.format_exc()
                        signals.error.emit(tb)

                try:
                    t = Thread(target=_worker_update, args=(site_id, upd), daemon=True)
                    t.start()
                except Exception:
                    try:
                        _worker_update(site_id, upd)
                    except Exception:
                        pass

            except Exception:
                pass

        try:
            update_btn.clicked.connect(_on_update)
        except Exception:
            pass
