from PyQt6 import QtWidgets, QtCore
import json


def setup(farm_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    """Initialize the farm page UI: populate `farmsTable` from Directus sites
    and wire selection to populate the form on the right.

    The main window is expected to expose `get_sites()` and the
    `dataLoaded` signal so we can refresh when data arrives.
    """
    try:
        if farm_page is None:
            return

        # find widgets
        farms_table = farm_page.findChild(QtWidgets.QTableWidget, "farmsTable")
        search_input = farm_page.findChild(QtWidgets.QLineEdit, "farmNameSearch")
        practice_combo = farm_page.findChild(QtWidgets.QComboBox, "practiceCombo")

        # form fields on the right
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
        seedling = farm_page.findChild(QtWidgets.QCheckBox, "seedlingCheck")
        compost = farm_page.findChild(QtWidgets.QCheckBox, "compostCheck")
        mulch = farm_page.findChild(QtWidgets.QCheckBox, "mulchCheck")
        fertilizer = farm_page.findChild(QtWidgets.QCheckBox, "fertilizerCheck")
        greenhouse = farm_page.findChild(QtWidgets.QCheckBox, "greenhouseCheck")
        remarks = farm_page.findChild(QtWidgets.QTextEdit, "remarksText")
        create_btn = farm_page.findChild(QtWidgets.QPushButton, "createRecord")

        # ensure table is configured
        try:
            if farms_table is not None:
                farms_table.setSelectionBehavior(
                    QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
                )
                farms_table.setSelectionMode(
                    QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
                )
                farms_table.setColumnCount(max(3, farms_table.columnCount()))
                # enforce column labels: Practice, Farm Name, Address
                try:
                    farms_table.setHorizontalHeaderLabels(
                        ["Practice", "Farm Name", "Address"]
                    )
                except Exception:
                    # fallback: leave existing headers
                    pass
        except Exception:
            pass

        def _get_sites_list():
            try:
                if main_window is None:
                    try:
                        if practice_input is not None:
                            practice_val = (
                                s.get("cultivation_practice")
                                or s.get("practice")
                                or s.get("farm_practice")
                                or None
                            )
                            if practice_val is not None:
                                pval = str(practice_val)
                                p_lower = pval.lower()
                                try:
                                    idx = practice_input.findData(p_lower)
                                except Exception:
                                    idx = -1
                                if idx is not None and idx >= 0:
                                    practice_input.setCurrentIndex(idx)
                                else:
                                    # if not present, add it with lowercase data and Title Case display
                                    try:
                                        practice_input.addItem(pval.title(), p_lower)
                                        practice_input.setCurrentIndex(
                                            practice_input.count() - 1
                                        )
                                    except Exception:
                                        try:
                                            practice_input.addItem(pval)
                                            practice_input.setCurrentIndex(
                                                practice_input.count() - 1
                                            )
                                        except Exception:
                                            pass
                    except Exception:
                        pass
                if farms_table is None:
                    return
                farms_table.setRowCount(0)
                practices = set()
                for s in items:
                    r = farms_table.rowCount()
                    farms_table.insertRow(r)
                    # practice (col 0)
                    practice = (
                        s.get("cultivation_practice")
                        or s.get("practice")
                        or s.get("farm_practice")
                        or s.get("practice_type")
                        or ""
                    )
                    try:
                        if practice:
                            practices.add(str(practice))
                    except Exception:
                        pass
                    try:
                        farms_table.setItem(
                            r, 0, QtWidgets.QTableWidgetItem(str(practice))
                        )
                    except Exception:
                        pass

                    # farm name (col 1)
                    name = s.get("name") or s.get("title") or s.get("site_name") or ""
                    item_name = QtWidgets.QTableWidgetItem(str(name))
                    # attach full site data for mapping
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

                    # address (col 2)
                    addr = s.get("address") or s.get("location") or ""
                    try:
                        farms_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(addr)))
                    except Exception:
                        pass

                # resize columns to contents
                try:
                    farms_table.resizeColumnsToContents()
                except Exception:
                    pass
                # populate practice combo with unique values (if widget exists)
                try:
                    if practice_combo is not None:
                        practice_combo.blockSignals(True)
                        practice_combo.clear()
                        # keep a blank first option (no associated data)
                        practice_combo.addItem("")
                        for p in sorted(practices):
                            try:
                                disp = str(p).title()
                                data = str(p).lower()
                                practice_combo.addItem(disp, data)
                            except Exception:
                                try:
                                    practice_combo.addItem(str(p))
                                except Exception:
                                    pass
                        practice_combo.blockSignals(False)
                except Exception:
                    pass
            except Exception:
                pass

        def _fill_form_from_site(s):
            try:
                if s is None:
                    return
                # if s is a JSON string, try to parse
                if isinstance(s, str):
                    try:
                        s = json.loads(s)
                    except Exception:
                        s = {"raw": s}

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
                    farm_name,
                    s.get("site_name") or s.get("name") or s.get("title") or "",
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
                # water_source -> checkboxes in waterSourceGroup
                try:
                    ws = (
                        s.get("water_source") or s.get("waterSources") or s.get("water")
                    )
                    if ws is None:
                        ws_list = []
                    elif isinstance(ws, list):
                        ws_list = [str(x).lower() for x in ws if x]
                    else:
                        ws_list = [str(ws).lower()]

                    def _apply_group_checks(
                        group: QtWidgets.QGroupBox, values: list[str]
                    ):
                        try:
                            if group is None:
                                return
                            # find all checkboxes inside the group
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
                                        # match by substring or token membership
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

                # soil texture -> soilTextureCombo (try to match available items)
                try:
                    soil_val = (
                        s.get("soil_type") or s.get("soil_texture") or s.get("soil")
                    )
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
                            # if no match, set editable text if combo is editable
                            try:
                                if soil_combo.isEditable():
                                    soil_combo.setEditText(str(soil_val))
                            except Exception:
                                pass
                except Exception:
                    pass
                _set_line(
                    crops_input,
                    (
                        ",".join(s.get("crops"))
                        if isinstance(s.get("crops"), list)
                        else s.get("crops") or ""
                    ),
                )
                try:
                    if practice_input is not None:
                        practice_val = (
                            s.get("cultivation_practice")
                            or s.get("practice")
                            or s.get("farm_practice")
                            or None
                        )
                        if practice_val is not None:
                            idx = practice_input.findText(str(practice_val))
                            if idx >= 0:
                                practice_input.setCurrentIndex(idx)
                            else:
                                # if not present, add it and select
                                try:
                                    practice_input.addItem(str(practice_val))
                                    practice_input.setCurrentIndex(
                                        practice_input.count() - 1
                                    )
                                except Exception:
                                    pass
                except Exception:
                    pass

                # checkboxes
                try:

                    # legacy boolean fields mapping (keep for backward compatibility)
                    def _set_check(cb, key):
                        try:
                            if cb is None:
                                return
                            v = s.get(key)
                            cb.setChecked(bool(v))
                        except Exception:
                            pass

                    _set_check(seedling, "seedling_trays")
                    _set_check(compost, "compost_with_plastic")
                    _set_check(mulch, "plastic_mulching")
                    _set_check(fertilizer, "fertilizer_sacks")
                    _set_check(greenhouse, "greenhouse_sheets")

                    # plastic_activity -> checkboxes inside plasticActGroup
                    try:
                        pa = s.get("plastic_activity") or s.get("plastic_activities")
                        if pa is None:
                            pa_list = []
                        elif isinstance(pa, list):
                            pa_list = [str(x).lower() for x in pa if x]
                        else:
                            pa_list = [str(pa).lower()]

                        plastic_group = farm_page.findChild(
                            QtWidgets.QGroupBox, "plasticActGroup"
                        )
                        try:
                            _apply_group_checks(plastic_group, pa_list)
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
                pass

        # handle row selection -> populate form
        def on_table_selection_changed():
            try:
                if farms_table is None:
                    return
                sels = farms_table.selectionModel().selectedRows()
                if not sels:
                    return
                idx = sels[0].row()
                # the full site JSON is stored on the Farm Name cell (column 1)
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
                    lambda sel, des: on_table_selection_changed()
                )
            except Exception:
                pass

        # search filter
        def on_search_change(text):
            try:
                txt = (text or "").strip().lower()
                for r in range(farms_table.rowCount()):
                    try:
                        item = farms_table.item(r, 1)
                        if item is None:
                            farms_table.setRowHidden(r, False)
                            continue
                        name = (item.text() or "").lower()
                        farms_table.setRowHidden(r, txt not in name)
                    except Exception:
                        pass
            except Exception:
                pass

        if search_input is not None:
            try:
                search_input.textChanged.connect(on_search_change)
            except Exception:
                pass

        # practice filter: supports either QComboBox (select) or QLineEdit (type-to-filter)
        try:
            practice_filter = farm_page.findChild(
                QtWidgets.QComboBox, "practiceComboSearch"
            ) or farm_page.findChild(QtWidgets.QLineEdit, "practiceComboSearch")

            def on_practice_filter_change(val=None):
                try:
                    if farms_table is None:
                        return
                    # determine filter text
                    txt = ""
                    if isinstance(practice_filter, QtWidgets.QComboBox):
                        try:
                            # prefer stored data (lowercase) if available
                            data = practice_filter.currentData()
                            if data is None:
                                txt = (
                                    (practice_filter.currentText() or "")
                                    .strip()
                                    .lower()
                                )
                            else:
                                txt = str(data).strip().lower()
                        except Exception:
                            txt = (practice_filter.currentText() or "").strip().lower()
                    else:
                        # QLineEdit
                        txt = (practice_filter.text() or "").strip().lower()

                    for r in range(farms_table.rowCount()):
                        try:
                            item = farms_table.item(r, 0)
                            if item is None:
                                farms_table.setRowHidden(r, False)
                                continue
                            practice_val = (item.text() or "").strip().lower()
                            # if txt empty -> show, else show rows containing txt
                            farms_table.setRowHidden(
                                r, bool(txt) and (txt not in practice_val)
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

            if practice_filter is not None:
                try:
                    if isinstance(practice_filter, QtWidgets.QComboBox):
                        practice_filter.currentIndexChanged.connect(
                            on_practice_filter_change
                        )
                    else:
                        practice_filter.textChanged.connect(on_practice_filter_change)
                except Exception:
                    pass
        except Exception:
            pass

        # refresh when dataLoaded called on main window
        try:
            if main_window is not None:
                try:
                    main_window.dataLoaded.connect(populate_table)
                except Exception:
                    pass
        except Exception:
            pass

        # initial population
        try:
            populate_table()
        except Exception:
            pass

        # optional: createRecord button behavior (clear form)
        try:
            if create_btn is not None:

                def _on_create():
                    try:
                        # clear form for new entry
                        _fill_form_from_site({})
                        farms_table.clearSelection()
                    except Exception:
                        pass

                try:
                    create_btn.clicked.connect(_on_create)
                except Exception:
                    pass
        except Exception:
            pass

    except Exception:
        pass
