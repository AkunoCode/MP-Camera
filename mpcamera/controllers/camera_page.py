from PyQt6 import QtWidgets, QtCore, QtGui
from threading import Thread
import json
import pathlib
import os
import traceback
import numpy as np
import cv2

try:
    from mpcamera.services.roboflow import RoboflowClient
except Exception:
    RoboflowClient = None

from mpcamera.utils.camera_utils import (
    append_log,
    color_for_label,
    extract_directus_items,
    get_site_id_from_sample,
)
from mpcamera.utils.prediction_utils import (
    find_predictions,
    extract_points_from_prediction,
)
from mpcamera.ui.overlays import (
    HoverEllipse,
    HoverPolygon,
    render_predictions_on_scene,
    show_debug_overlays,
)
from mpcamera.ui.overlays import ensure_overlay_for_view
from mpcamera.utils.inference_utils import parse_result_to_preds, compute_aggregates
from mpcamera.utils.color_utils import get_color_name


# Directus and site helpers are provided by `camera_utils` service


def setup(camera_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    """Set up `camera_page` UI using Directus data available on `main_window`.

    This populates `farmCombo` and `soilCombo` and wires their interactions.
    """
    try:
        farm_combo = camera_page.findChild(QtWidgets.QComboBox, "farmCombo")
        soil_combo = camera_page.findChild(QtWidgets.QComboBox, "soilCombo")

        def populate_from_cache():
            sites = extract_directus_items(main_window.get_sites())
            soils = extract_directus_items(main_window.get_soilsamples())

            # store raw lists on the main window for other modules that may want them
            setattr(main_window, "_camera_sites_list", sites)
            setattr(main_window, "_camera_soils_list", soils)

            # populate farms
            if farm_combo is not None:
                try:
                    farm_combo.blockSignals(True)
                    farm_combo.clear()
                    for item in sites:
                        name = (
                            item.get("site_name")
                            or item.get("name")
                            or item.get("title")
                            or str(item.get("id"))
                        )
                        farm_combo.addItem(str(name), item.get("id"))
                    try:
                        farm_combo.setCurrentIndex(-1)
                    except Exception:
                        pass
                    farm_combo.blockSignals(False)
                    print(f"Populated farmCombo with {len(sites)} entries")
                except Exception as e:
                    print("camera_page: Failed to populate farmCombo:", e)

            # populate soils (initially all)
            if soil_combo is not None:
                try:
                    _populate_soil_combo(site_id=None)
                    try:
                        soil_combo.setCurrentIndex(-1)
                    except Exception:
                        pass
                except Exception as e:
                    print("camera_page: Failed to populate soilCombo:", e)

        def _populate_soil_combo(site_id=None):
            soils = getattr(main_window, "_camera_soils_list", []) or []
            if soil_combo is None:
                return
            soil_combo.blockSignals(True)
            soil_combo.clear()
            count = 0
            for item in soils:
                s_site = get_site_id_from_sample(item)
                if site_id is None or site_id == s_site:
                    sid = item.get("id")
                    date = item.get("date_collected") or item.get("date") or ""
                    label = f"Sample ID {sid} ({date})"
                    soil_combo.addItem(label, sid)
                    count += 1
            soil_combo.blockSignals(False)
            print(
                f"Populated soilCombo with {count} entries (filter site_id={site_id})"
            )

        def on_farm_changed():
            try:
                site_id = farm_combo.currentData()
                site_id = site_id if site_id else None
                _populate_soil_combo(site_id)
            except Exception as e:
                print("camera_page: Error handling farm change:", e)

        def on_soil_changed():
            try:
                sid = soil_combo.currentData()
                if not sid:
                    return
                soils = getattr(main_window, "_camera_soils_list", []) or []
                match = None
                for item in soils:
                    if item.get("id") == sid:
                        match = item
                        break
                if match is None:
                    return
                site_id = get_site_id_from_sample(match)
                if site_id is None:
                    return
                # set farm selection to corresponding site if present
                try:
                    idx = farm_combo.findData(site_id)
                    if idx != -1:
                        farm_combo.setCurrentIndex(idx)
                except Exception:
                    pass
            except Exception as e:
                print("camera_page: Error handling soil change:", e)

        # If data already present, populate immediately, otherwise wait for main signal
        try:
            if (
                main_window.get_sites() is not None
                and main_window.get_soilsamples() is not None
            ):
                populate_from_cache()
            else:
                try:
                    main_window.dataLoaded.connect(populate_from_cache)
                except Exception:
                    pass
        except Exception as e:
            print("camera_page: scheduling population failed:", e)

        # wire signals
        try:
            if farm_combo is not None:
                farm_combo.currentIndexChanged.connect(lambda _: on_farm_changed())
            if soil_combo is not None:
                soil_combo.currentIndexChanged.connect(lambda _: on_soil_changed())
        except Exception as e:
            print("camera_page: failed to connect combo signals:", e)

        # Image upload -> show in QGraphicsView named 'cameraView'
        try:
            img_btn = camera_page.findChild(QtWidgets.QPushButton, "imgUploadButton")
            cam_view = camera_page.findChild(QtWidgets.QGraphicsView, "cameraView")

            # ensure mouse move events are delivered to the view and its viewport
            # so QGraphicsItems that rely on hover events receive them
            try:
                if cam_view is not None:
                    try:
                        cam_view.setMouseTracking(True)
                    except Exception:
                        pass
                    try:
                        vp = cam_view.viewport()
                        if vp is not None:
                            vp.setMouseTracking(True)
                    except Exception:
                        pass
            except Exception:
                pass

            # Create a simple overlay widget that will be shown on top of the camera view
            overlay = None

            # overlay creation moved to overlays service: use ensure_overlay_for_view

            # use module-level _color_for_label

            def _show_image_in_view(path: str):
                try:
                    if not path:
                        return
                    print(f"camera_page: _show_image_in_view called with: {path}")
                    pix = QtGui.QPixmap(path)
                    if pix.isNull():
                        print("camera_page: failed to load image", path)
                        return
                    scene = QtWidgets.QGraphicsScene()
                    scene.addPixmap(pix)
                    print("camera_page: pixmap added to scene")
                    if cam_view is not None:
                        cam_view.setScene(scene)
                        cam_view.setRenderHints(
                            QtGui.QPainter.RenderHint.SmoothPixmapTransform
                            | QtGui.QPainter.RenderHint.Antialiasing
                        )
                        try:
                            si = len(scene.items())
                            print(
                                f"camera_page: scene has {si} items after adding pixmap"
                            )
                        except Exception:
                            pass
                        # fit the image into the view while keeping aspect ratio
                        try:
                            rect = scene.itemsBoundingRect()
                            cam_view.fitInView(
                                rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio
                            )
                        except Exception:
                            pass

                    # If the Roboflow service isn't available at runtime, draw some debug overlays
                    # so the developer can verify the drawing code and translucent fill.
                    try:
                        print(
                            f"camera_page: RoboflowClient is {'available' if RoboflowClient is not None else 'MISSING'}"
                        )
                        if (
                            RoboflowClient is None
                            and cam_view is not None
                            and cam_view.scene() is not None
                        ):
                            pix_item = None
                            try:
                                for it in cam_view.scene().items():
                                    try:
                                        from PyQt6 import QtWidgets as _qtw

                                        if isinstance(it, _qtw.QGraphicsPixmapItem):
                                            pix_item = it
                                            break
                                    except Exception:
                                        pass
                            except Exception:
                                pix_item = None
                            if pix_item is not None:
                                print(
                                    "camera_page: found pixmap item for debug overlays"
                                )
                                try:
                                    try:
                                        show_debug_overlays(cam_view.scene(), pix_item)
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    # send to Roboflow inference asynchronously (if service available)
                    try:
                        if RoboflowClient is not None:
                            # show overlay while inference runs
                            ov = ensure_overlay_for_view(cam_view)
                            try:
                                if ov is not None:
                                    try:
                                        if getattr(ov, "_spinner", None) is not None:
                                            try:
                                                ov._spinner.start()
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                    ov.show()
                            except Exception:
                                pass

                            class _OverlayNotifier(QtCore.QObject):
                                # emit the inference result object when ready
                                finished = QtCore.pyqtSignal(object)

                            notifier = _OverlayNotifier()

                            def _handle_inference_result(result):
                                # hide overlay and stop spinner, then draw overlays on the scene
                                try:
                                    try:
                                        if getattr(ov, "_spinner", None) is not None:
                                            ov._spinner.stop()
                                    except Exception:
                                        pass
                                    try:
                                        ov.hide()
                                    except Exception:
                                        pass
                                except Exception:
                                    pass

                                # draw points and labels on the scene via overlay service
                                try:
                                    scene = (
                                        cam_view.scene()
                                        if cam_view is not None
                                        else None
                                    )
                                    if scene is None:
                                        return
                                    try:
                                        render_predictions_on_scene(scene, result)
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                                # update inference table and counters
                                try:
                                    try:
                                        preds = parse_result_to_preds(result)
                                    except Exception:
                                        preds = []

                                    # write debug dump to prediction_debug.txt for troubleshooting
                                    try:
                                        dbg_path = (
                                            pathlib.Path(__file__).resolve().parents[1]
                                            / "prediction_debug.txt"
                                        )
                                        with open(
                                            dbg_path, "a", encoding="utf-8"
                                        ) as _dbg:
                                            _dbg.write("--- INFERENCE RUN ---\n")
                                            try:
                                                _dbg.write("RAW_RESULT:\n")
                                                _dbg.write(
                                                    json.dumps(result, default=str)
                                                    + "\n"
                                                )
                                            except Exception:
                                                try:
                                                    _dbg.write(str(result) + "\n")
                                                except Exception:
                                                    _dbg.write(
                                                        "<unserializable raw result>\n"
                                                    )
                                            try:
                                                _dbg.write(
                                                    f"PARSED_PRED_COUNT: {len(preds)}\n"
                                                )
                                                _dbg.write("PARSED_PRED_ITEMS:\n")
                                                _dbg.write(
                                                    json.dumps(preds, default=str)
                                                    + "\n"
                                                )
                                            except Exception:
                                                try:
                                                    _dbg.write(str(preds) + "\n")
                                                except Exception:
                                                    _dbg.write(
                                                        "<unserializable preds>\n"
                                                    )
                                    except Exception:
                                        pass

                                    # populate inferenceTable
                                    try:
                                        inf_table = camera_page.findChild(
                                            QtWidgets.QTableWidget, "inferenceTable"
                                        )
                                        if inf_table is not None:
                                            # try to obtain the image numpy array from the scene's pixmap
                                            img_np = None
                                            try:

                                                def _qimage_to_numpy(
                                                    qimg: QtGui.QImage,
                                                ):
                                                    # convert to a known RGB or RGBA format
                                                    fmt = qimg.format()
                                                    # prefer RGB888 or RGBA8888
                                                    if (
                                                        fmt
                                                        != QtGui.QImage.Format.Format_RGB888
                                                        and fmt
                                                        != QtGui.QImage.Format.Format_RGBA8888
                                                    ):
                                                        try:
                                                            qimg = qimg.convertToFormat(
                                                                QtGui.QImage.Format.Format_RGB888
                                                            )
                                                        except Exception:
                                                            try:
                                                                qimg = qimg.convertToFormat(
                                                                    QtGui.QImage.Format.Format_RGBA8888
                                                                )
                                                            except Exception:
                                                                pass

                                                    w = qimg.width()
                                                    h = qimg.height()
                                                    channels = 3
                                                    fmt = qimg.format()
                                                    if (
                                                        fmt
                                                        == QtGui.QImage.Format.Format_RGBA8888
                                                    ):
                                                        channels = 4

                                                    ptr = qimg.bits()
                                                    ptr.setsize(qimg.byteCount())
                                                    arr = np.frombuffer(
                                                        ptr, dtype=np.uint8
                                                    )
                                                    # account for possible scanline padding
                                                    bytes_per_line = qimg.bytesPerLine()
                                                    if bytes_per_line == w * channels:
                                                        arr = arr.reshape(
                                                            (h, w, channels)
                                                        )
                                                    else:
                                                        # reshape to (h, bytes_per_line) then slice
                                                        arr = arr.reshape(
                                                            (h, bytes_per_line)
                                                        )
                                                        arr = arr[:, : w * channels]
                                                        arr = arr.reshape(
                                                            (h, w, channels)
                                                        )

                                                    # if RGBA, drop alpha
                                                    if channels == 4:
                                                        arr = arr[:, :, :3]

                                                    # QImage.Format_RGB888 is already RGB order
                                                    return arr.copy()

                                                pix_item = None
                                                for it in scene.items():
                                                    try:
                                                        from PyQt6 import (
                                                            QtWidgets as _qtw,
                                                        )

                                                        if isinstance(
                                                            it, _qtw.QGraphicsPixmapItem
                                                        ):
                                                            pix_item = it
                                                            break
                                                    except Exception:
                                                        if hasattr(it, "pixmap"):
                                                            pix_item = it
                                                            break
                                                if pix_item is not None:
                                                    qimg = pix_item.pixmap().toImage()
                                                    try:
                                                        img_np = _qimage_to_numpy(qimg)
                                                    except Exception:
                                                        img_np = None
                                                # fallback: if QGraphicsPixmapItem not present, try loading from original path
                                                if img_np is None:
                                                    try:
                                                        if path and os.path.exists(
                                                            path
                                                        ):
                                                            # read with cv2 (BGR) then convert to RGB
                                                            bgr = cv2.imread(path)
                                                            if bgr is not None:
                                                                try:
                                                                    rgb = cv2.cvtColor(
                                                                        bgr,
                                                                        cv2.COLOR_BGR2RGB,
                                                                    )
                                                                except Exception:
                                                                    rgb = bgr[
                                                                        :, :, ::-1
                                                                    ]
                                                                img_np = rgb
                                                                # debug write
                                                                try:
                                                                    dbg_path = (
                                                                        pathlib.Path(
                                                                            __file__
                                                                        )
                                                                        .resolve()
                                                                        .parents[1]
                                                                        / "prediction_debug.txt"
                                                                    )
                                                                    with open(
                                                                        dbg_path,
                                                                        "a",
                                                                        encoding="utf-8",
                                                                    ) as _dbg:
                                                                        _dbg.write(
                                                                            f"COLOR_DEBUG: loaded_image_from_path: {path}\n"
                                                                        )
                                                                        _dbg.write(
                                                                            f"loaded_image_shape: {img_np.shape if img_np is not None else None}\n"
                                                                        )
                                                                except Exception:
                                                                    pass
                                                    except Exception:
                                                        pass
                                            except Exception:
                                                img_np = None
                                            inf_table.setRowCount(0)
                                            for p in preds:
                                                r = inf_table.rowCount()
                                                inf_table.insertRow(r)
                                                # Shape
                                                try:
                                                    inf_table.setItem(
                                                        r,
                                                        0,
                                                        QtWidgets.QTableWidgetItem(
                                                            str(p.get("label") or "")
                                                        ),
                                                    )
                                                except Exception:
                                                    pass
                                                # Confidence
                                                try:
                                                    sc = p.get("score")
                                                    sc_text = (
                                                        f"{float(sc):.2f}"
                                                        if sc is not None
                                                        else ""
                                                    )
                                                    inf_table.setItem(
                                                        r,
                                                        1,
                                                        QtWidgets.QTableWidgetItem(
                                                            sc_text
                                                        ),
                                                    )
                                                except Exception:
                                                    pass
                                                # Color: compute using masked pixels if available
                                                try:
                                                    col_text = ""
                                                    try:
                                                        if img_np is not None:
                                                            raw = p.get("raw") or {}
                                                            mask_input = (
                                                                p.get("points")
                                                                or raw.get(
                                                                    "segmentation"
                                                                )
                                                                or raw.get("mask")
                                                            )
                                                            if mask_input:
                                                                try:
                                                                    col_text = (
                                                                        get_color_name(
                                                                            img_np,
                                                                            mask_input,
                                                                        )
                                                                    )
                                                                except Exception:
                                                                    col_text = ""
                                                            else:
                                                                col_text = ""
                                                        else:
                                                            col_text = ""
                                                    except Exception:
                                                        col_text = ""
                                                    # write debug info about color computation
                                                    try:
                                                        dbg_path = (
                                                            pathlib.Path(__file__)
                                                            .resolve()
                                                            .parents[1]
                                                            / "prediction_debug.txt"
                                                        )
                                                        with open(
                                                            dbg_path,
                                                            "a",
                                                            encoding="utf-8",
                                                        ) as _dbg:
                                                            _dbg.write("COLOR_DEBUG:\n")
                                                            _dbg.write(
                                                                f"has_image_np: {img_np is not None}\n"
                                                            )
                                                            try:
                                                                _dbg.write(
                                                                    f"mask_input_type: {type(mask_input)}\n"
                                                                )
                                                            except Exception:
                                                                _dbg.write(
                                                                    "mask_input_type: <err>\n"
                                                                )
                                                            _dbg.write(
                                                                f"col_text: {col_text}\n"
                                                            )
                                                    except Exception:
                                                        pass
                                                    col_item = (
                                                        QtWidgets.QTableWidgetItem(
                                                            col_text
                                                        )
                                                    )
                                                    inf_table.setItem(r, 2, col_item)
                                                except Exception:
                                                    pass
                                                # Size (placeholder)
                                                try:
                                                    sz = p.get("size")
                                                    inf_table.setItem(
                                                        r,
                                                        3,
                                                        QtWidgets.QTableWidgetItem(
                                                            str(sz or "")
                                                        ),
                                                    )
                                                except Exception:
                                                    pass
                                    except Exception:
                                        pass

                                    # aggregates
                                    try:
                                        ag = compute_aggregates(preds)

                                        def _set_lbl(name, val):
                                            try:
                                                lbl = camera_page.findChild(
                                                    QtWidgets.QLabel, name
                                                )
                                                if lbl is not None:
                                                    lbl.setText(str(val))
                                            except Exception:
                                                pass

                                        _set_lbl("totalCount", ag.get("total", 0))
                                        ave = ag.get("ave_confidence")
                                        _set_lbl(
                                            "aveConfidence",
                                            f"{ave:.2f}" if ave is not None else "0.00",
                                        )
                                        cnts = ag.get("counts", {})
                                        _set_lbl(
                                            "fragmentsCount", cnts.get("fragment", 0)
                                        )
                                        _set_lbl("sheetsCount", cnts.get("sheet", 0))
                                        _set_lbl("fibersCount", cnts.get("fiber", 0))
                                        _set_lbl("foamsCount", cnts.get("foam", 0))
                                        _set_lbl("filmsCount", cnts.get("film", 0))
                                        _set_lbl("beadsCount", cnts.get("bead", 0))
                                    except Exception:
                                        pass
                                except Exception:
                                    pass

                            notifier.finished.connect(_handle_inference_result)

                            def _run_inference(p, note):
                                res = None
                                try:
                                    client = RoboflowClient.get_default()
                                    print("roboflow: sending image for inference ->", p)
                                    res = client.run_workflow(p)
                                    print("roboflow: inference result:", res)
                                except Exception:
                                    print(
                                        "roboflow: inference failed:\n",
                                        traceback.format_exc(),
                                    )
                                finally:
                                    try:
                                        note.finished.emit(res)
                                    except Exception:
                                        # fallback: try hiding overlay on main thread
                                        try:
                                            QtCore.QTimer.singleShot(
                                                0,
                                                lambda: (
                                                    ov.hide()
                                                    if ov is not None
                                                    else None
                                                ),
                                            )
                                        except Exception:
                                            pass

                            Thread(
                                target=_run_inference,
                                args=(path, notifier),
                                daemon=True,
                            ).start()
                        else:
                            print("roboflow: service not available (module missing)")
                    except Exception:
                        print(
                            "roboflow: failed to start inference thread:\n",
                            traceback.format_exc(),
                        )
                except Exception as e:
                    print("camera_page: error showing image in view:", e)

            def on_img_upload():
                try:
                    # ask user for image file
                    fname, _ = QtWidgets.QFileDialog.getOpenFileName(
                        camera_page,
                        "Select image",
                        "",
                        "Image Files (*.png *.jpg *.jpeg *.bmp);;All Files (*)",
                    )
                    if fname:
                        _show_image_in_view(fname)
                except Exception as e:
                    print("camera_page: img upload failed:", e)

            if img_btn is not None:
                try:
                    img_btn.clicked.connect(on_img_upload)
                except Exception as e:
                    print("camera_page: failed to connect imgUploadButton:", e)
            else:
                print("camera_page: imgUploadButton not found in UI")
        except Exception as e:
            print("camera_page: error wiring image upload:", e)

    except Exception as e:
        print("camera_page.setup failed:", e)
