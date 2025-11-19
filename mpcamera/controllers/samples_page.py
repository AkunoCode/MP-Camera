from PyQt6 import QtWidgets, QtCore
import json
from threading import Thread
import traceback
import datetime

try:
    from mpcamera.services.directus import DirectusClient
except Exception:
    DirectusClient = None


def setup(sample_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    """Initialize the samples page: populate `samplesTable` from Directus soilsamples
    and wire selection to populate the form on the right.
    """
    if sample_page is None:
        return

    samples_table = sample_page.findChild(QtWidgets.QTableWidget, "samplesTable")
    search_input = sample_page.findChild(QtWidgets.QLineEdit, "farmNameSearch")
    farm_combo = sample_page.findChild(QtWidgets.QComboBox, "farmNameCombo")
    date_edit = sample_page.findChild(QtWidgets.QDateEdit, "dateCollected")
    create_btn = sample_page.findChild(QtWidgets.QPushButton, "createRecord")
    update_btn = sample_page.findChild(QtWidgets.QPushButton, "updateRecord")

    if samples_table is not None:
        samples_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        samples_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
    # default date to today for easier creation
    try:
        if date_edit is not None:
            try:
                date_edit.setDate(QtCore.QDate.currentDate())
            except Exception:
                pass
    except Exception:
        pass

    def _get_samples_list():
        try:
            if main_window is None:
                return []
            samples = main_window.get_soilsamples() or []
            if isinstance(samples, dict) and "data" in samples:
                return samples.get("data") or []
            if isinstance(samples, list):
                return samples
            return []
        except Exception:
            return []

    def _get_sites_map():
        try:
            sites = main_window.get_sites() or []
            data = []
            if isinstance(sites, dict) and "data" in sites:
                data = sites.get("data") or []
            elif isinstance(sites, list):
                data = sites
            m = {}
            for s in data:
                try:
                    sid = s.get("id") or s.get("site_id")
                    m[sid] = s
                except Exception:
                    pass
            return m
        except Exception:
            return {}

    def populate_table():
        items = _get_samples_list()
        site_map = _get_sites_map()
        if samples_table is None:
            return
        try:
            samples_table.setSortingEnabled(False)
        except Exception:
            pass
        samples_table.setRowCount(0)
        for s in items:
            try:
                r = samples_table.rowCount()
                samples_table.insertRow(r)

                # farm name: try to resolve from relation or site_map
                farm_name = ""
                site_field = s.get("site") if isinstance(s, dict) else None
                site_obj = None
                if isinstance(site_field, dict):
                    # direct object
                    site_obj = site_field
                elif site_field in site_map:
                    site_obj = site_map.get(site_field)

                if isinstance(site_obj, dict):
                    farm_name = site_obj.get("site_name") or site_obj.get("name") or ""

                # fallback: check common sample fields
                if not farm_name:
                    farm_name = (
                        s.get("site_name")
                        or s.get("siteName")
                        or s.get("site_label")
                        or ""
                    )

                # date collected
                date_val = (
                    s.get("date_collected")
                    or s.get("dateCollected")
                    or s.get("collected")
                    or ""
                )

                # put farm name and date into table
                try:
                    item_farm = QtWidgets.QTableWidgetItem(str(farm_name))
                    # store full sample JSON on the row for later update
                    try:
                        item_farm.setData(
                            QtCore.Qt.ItemDataRole.UserRole, json.dumps(s, default=str)
                        )
                    except Exception:
                        try:
                            item_farm.setData(QtCore.Qt.ItemDataRole.UserRole, str(s))
                        except Exception:
                            pass
                    samples_table.setItem(r, 0, item_farm)
                except Exception:
                    pass

                try:
                    samples_table.setItem(
                        r, 1, QtWidgets.QTableWidgetItem(str(date_val))
                    )
                except Exception:
                    pass
            except Exception:
                pass

        try:
            samples_table.resizeColumnsToContents()
        except Exception:
            pass
        try:
            samples_table.setSortingEnabled(True)
        except Exception:
            pass

        # populate farm combo with sites (id as userData)
        try:
            farm_combo.blockSignals(True) if farm_combo is not None else None
            if farm_combo is not None:
                farm_combo.clear()
                farm_combo.addItem("", None)
                for sid, s in sorted(
                    _get_sites_map().items(),
                    key=lambda x: str(x[1].get("site_name") or x[1].get("name") or ""),
                ):
                    try:
                        display = s.get("site_name") or s.get("name") or str(sid)
                        farm_combo.addItem(str(display), sid)
                    except Exception:
                        pass
                farm_combo.blockSignals(False)
        except Exception:
            pass

    def update_create_button_label():
        try:
            if samples_table is None or create_btn is None:
                return
            sels = (
                samples_table.selectionModel().selectedRows()
                if samples_table is not None
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
            if samples_table is None:
                return
            sels = samples_table.selectionModel().selectedRows()
            update_create_button_label()
            if not sels:
                return
            idx = sels[0].row()
            it = samples_table.item(idx, 0)
            if it is None:
                return
            data = it.data(QtCore.Qt.ItemDataRole.UserRole)
            if data is None:
                return
            try:
                sample = json.loads(data)
            except Exception:
                sample = data

            # populate form
            try:
                site_field = sample.get("site") if isinstance(sample, dict) else None
                sid = None
                if isinstance(site_field, dict):
                    sid = site_field.get("id") or site_field.get("site_id")
                else:
                    try:
                        sid = int(site_field)
                    except Exception:
                        sid = site_field
                # set farm combo by userData
                if farm_combo is not None:
                    try:
                        # find index with that userData
                        found = -1
                        for i in range(farm_combo.count()):
                            try:
                                if farm_combo.itemData(i) == sid:
                                    found = i
                                    break
                            except Exception:
                                pass
                        if found >= 0:
                            farm_combo.setCurrentIndex(found)
                    except Exception:
                        pass

                # date
                try:
                    dstr = (
                        sample.get("date_collected")
                        or sample.get("dateCollected")
                        or sample.get("collected")
                    )
                    if dstr and date_edit is not None:
                        parsed = None
                        # If it's already a date/datetime object
                        try:
                            if isinstance(dstr, datetime.date):
                                parsed = QtCore.QDate(dstr.year, dstr.month, dstr.day)
                        except Exception:
                            pass

                        s = str(dstr).strip() if parsed is None else None
                        if parsed is None and s:
                            # If ISO datetime with time, split at 'T' and take date part
                            if "T" in s:
                                s = s.split("T")[0]
                            # If contains timezone Z or offset, strip it (we only need the date)
                            if s.endswith("Z"):
                                s = s[:-1]
                            # try regex to extract YYYY-MM-DD or DD-MM-YYYY
                            import re

                            m_iso = re.search(r"(\d{4}-\d{2}-\d{2})", s)
                            if m_iso:
                                s_date = m_iso.group(1)
                                try:
                                    dt = datetime.datetime.strptime(s_date, "%Y-%m-%d")
                                    parsed = QtCore.QDate(dt.year, dt.month, dt.day)
                                except Exception:
                                    pass
                            else:
                                m_eu = re.search(r"(\d{2}-\d{2}-\d{4})", s)
                                if m_eu:
                                    s_date = m_eu.group(1)
                                    try:
                                        dt = datetime.datetime.strptime(
                                            s_date, "%d-%m-%Y"
                                        )
                                        parsed = QtCore.QDate(dt.year, dt.month, dt.day)
                                    except Exception:
                                        pass

                        # fallback parsing attempts
                        if parsed is None and s:
                            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
                                try:
                                    dt = datetime.datetime.strptime(s, fmt)
                                    parsed = QtCore.QDate(dt.year, dt.month, dt.day)
                                    break
                                except Exception:
                                    pass

                        if parsed is None and s:
                            try:
                                qd = QtCore.QDate.fromString(s, "yyyy-MM-dd")
                                if qd.isValid():
                                    parsed = qd
                            except Exception:
                                pass

                        if parsed is None and s:
                            try:
                                qd2 = QtCore.QDate.fromString(
                                    s, QtCore.Qt.DateFormat.ISODate
                                )
                                if qd2.isValid():
                                    parsed = qd2
                            except Exception:
                                pass

                        if parsed is not None:
                            try:
                                date_edit.setDate(parsed)
                            except Exception:
                                pass
                except Exception:
                    pass
            except Exception:
                pass

        except Exception:
            pass

    if samples_table is not None:
        try:
            samples_table.selectionModel().selectionChanged.connect(
                lambda s, d: on_table_selection_changed()
            )
            update_create_button_label()
        except Exception:
            pass

    # search
    if search_input is not None and samples_table is not None:
        try:

            def on_search_change(text):
                try:
                    txt = (text or "").strip().lower()
                    for r in range(samples_table.rowCount()):
                        try:
                            item = samples_table.item(r, 0)
                            if item is None:
                                samples_table.setRowHidden(r, False)
                                continue
                            name = (item.text() or "").lower()
                            samples_table.setRowHidden(r, txt not in name)
                        except Exception:
                            pass
                except Exception:
                    pass

            search_input.textChanged.connect(on_search_change)
        except Exception:
            pass

    # connect dataLoaded to populate
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
            title = "Created Sample" if action != "update" else "Updated Sample"
            text = (
                "Sample created successfully"
                if action != "update"
                else "Sample updated successfully"
            )
            QtWidgets.QMessageBox.information(sample_page, title, text)
        except Exception:
            pass
        try:
            # clear form
            if farm_combo is not None:
                try:
                    farm_combo.setCurrentIndex(0)
                except Exception:
                    pass
            if date_edit is not None:
                try:
                    date_edit.setDate(QtCore.QDate.currentDate())
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if samples_table is not None:
                samples_table.clearSelection()
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
                sample_page, "Operation Failed", "See console for details."
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

    try:
        signals.success.connect(_handle_worker_success)
        signals.error.connect(_handle_worker_error)
    except Exception:
        pass

    # Create behavior
    if create_btn is not None:

        def _on_create():
            try:
                # if selection exists -> unselect + clear
                try:
                    sels = (
                        samples_table.selectionModel().selectedRows()
                        if samples_table is not None
                        else []
                    )
                except Exception:
                    sels = []
                if sels:
                    try:
                        samples_table.clearSelection()
                        # clear form
                        if farm_combo is not None:
                            farm_combo.setCurrentIndex(0)
                        if date_edit is not None:
                            date_edit.setDate(QtCore.QDate.currentDate())
                        update_create_button_label()
                        return
                    except Exception:
                        pass

                if DirectusClient is None:
                    try:
                        QtWidgets.QMessageBox.information(
                            sample_page,
                            "Directus Not Configured",
                            "Directus client not available.",
                        )
                    except Exception:
                        pass
                    return

                # gather fields
                item = {}
                try:
                    # farm id from combo userData
                    site_id = None
                    if farm_combo is not None:
                        try:
                            site_id = farm_combo.currentData()
                        except Exception:
                            site_id = None
                    item["site"] = site_id
                    # date
                    if date_edit is not None:
                        try:
                            d = date_edit.date()
                            item["date_collected"] = d.toString("yyyy-MM-dd")
                        except Exception:
                            item["date_collected"] = ""
                except Exception:
                    pass

                # validate
                missing = []
                if not item.get("site"):
                    missing.append("Farm")
                if not item.get("date_collected"):
                    missing.append("Date Collected")
                if missing:
                    try:
                        QtWidgets.QMessageBox.warning(
                            sample_page,
                            "Validation Error",
                            "Please fill required fields: " + ", ".join(missing),
                        )
                    except Exception:
                        pass
                    return

                try:
                    create_btn.setEnabled(False)
                except Exception:
                    pass

                def _worker_post(itm):
                    try:
                        client = DirectusClient()
                        resp = client.create_soilsample(itm)
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
                try:
                    sels = (
                        samples_table.selectionModel().selectedRows()
                        if samples_table is not None
                        else []
                    )
                except Exception:
                    sels = []
                if not sels:
                    try:
                        QtWidgets.QMessageBox.warning(
                            sample_page,
                            "No Selection",
                            "Please select a sample to update.",
                        )
                    except Exception:
                        pass
                    return
                idx = sels[0].row()
                it = samples_table.item(idx, 0)
                if it is None:
                    try:
                        QtWidgets.QMessageBox.warning(
                            sample_page, "No Data", "Selected row has no sample data."
                        )
                    except Exception:
                        pass
                    return
                data = it.data(QtCore.Qt.ItemDataRole.UserRole)
                try:
                    sample = json.loads(data)
                except Exception:
                    sample = data
                sample_id = None
                if isinstance(sample, dict):
                    sample_id = sample.get("id") or sample.get("sample_id")
                if not sample_id:
                    try:
                        QtWidgets.QMessageBox.warning(
                            sample_page,
                            "Missing ID",
                            "Cannot determine sample id for update.",
                        )
                    except Exception:
                        pass
                    return

                upd = {}
                try:
                    # site id from combo
                    site_id = None
                    if farm_combo is not None:
                        try:
                            site_id = farm_combo.currentData()
                        except Exception:
                            site_id = None
                    upd["site"] = site_id
                    if date_edit is not None:
                        try:
                            d = date_edit.date()
                            upd["date_collected"] = d.toString("yyyy-MM-dd")
                        except Exception:
                            upd["date_collected"] = ""
                except Exception:
                    pass

                missing = []
                if not upd.get("site"):
                    missing.append("Farm")
                if not upd.get("date_collected"):
                    missing.append("Date Collected")
                if missing:
                    try:
                        QtWidgets.QMessageBox.warning(
                            sample_page,
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
                        resp = client.update_soilsample(sid, payload)
                        signals.success.emit(("update", resp))
                    except Exception:
                        tb = traceback.format_exc()
                        signals.error.emit(tb)

                try:
                    t = Thread(
                        target=_worker_update, args=(sample_id, upd), daemon=True
                    )
                    t.start()
                except Exception:
                    try:
                        _worker_update(sample_id, upd)
                    except Exception:
                        pass

            except Exception:
                pass

        try:
            update_btn.clicked.connect(_on_update)
        except Exception:
            pass
