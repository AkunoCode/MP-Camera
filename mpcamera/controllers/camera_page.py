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
import tempfile
import uuid
from mpcamera.utils.inference_utils import parse_result_to_preds, compute_aggregates
from mpcamera.utils.color_utils import get_color_name
from mpcamera.utils.um_per_pixel import calculate_micrometers_per_pixel
from mpcamera.utils.morphometrics import (
    calculate_area_um2,
    calculate_perimeter_um,
    calculate_major_axis_um,
    calculate_minor_axis_um,
    calculate_equivalent_circular_diameter,
    calculate_skeleton_length_um,
)


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
            # model selection combo (choose Roboflow workflow)
            model_combo = camera_page.findChild(QtWidgets.QComboBox, "modelCombo")
            try:
                # list of (display_name, workflow_id)
                _model_workflows = [
                    ("YOLOv11", "detect-count-and-visualize-2"),
                    ("RF-DETR-SEG", "detect-count-and-visualize"),
                ]
                if model_combo is not None:
                    model_combo.blockSignals(True)
                    model_combo.clear()
                    for disp, wf in _model_workflows:
                        try:
                            model_combo.addItem(disp, wf)
                        except Exception:
                            try:
                                # fallback: add without data
                                model_combo.addItem(disp)
                            except Exception:
                                pass

                    # try to select currently-configured workflow from RoboflowClient
                    try:
                        current_wf = None
                        if RoboflowClient is not None:
                            try:
                                current_wf = RoboflowClient.get_default().workflow
                            except Exception:
                                current_wf = None
                        if current_wf:
                            sel_idx = -1
                            for i in range(model_combo.count()):
                                try:
                                    if model_combo.itemData(i) == current_wf:
                                        sel_idx = i
                                        break
                                except Exception:
                                    pass
                            try:
                                if sel_idx != -1:
                                    model_combo.setCurrentIndex(sel_idx)
                                else:
                                    model_combo.setCurrentIndex(0)
                            except Exception:
                                pass
                        else:
                            try:
                                model_combo.setCurrentIndex(0)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    model_combo.blockSignals(False)

                    # connect selection change to update the Roboflow workflow used
                    try:

                        def _on_model_changed(idx):
                            try:
                                wf = None
                                try:
                                    wf = model_combo.itemData(idx)
                                except Exception:
                                    wf = None
                                if wf is None:
                                    return
                                if RoboflowClient is not None:
                                    try:
                                        RoboflowClient.get_default().workflow = wf
                                        print(
                                            "camera_page: Roboflow workflow set to", wf
                                        )
                                    except Exception:
                                        pass

                                # If there's an image or stream active, trigger an immediate inference
                                try:
                                    scene = (
                                        cam_view.scene()
                                        if cam_view is not None
                                        else None
                                    )
                                    has_scene = (
                                        scene is not None and len(scene.items()) > 0
                                    )
                                except Exception:
                                    has_scene = False

                                try:
                                    streaming = getattr(
                                        camera_page, "_streaming", False
                                    )
                                    # prepare pixmap (prefer last_pixmap when streaming)
                                    pix = None
                                    if streaming:
                                        pix = getattr(camera_page, "_last_pixmap", None)
                                    if pix is None and has_scene:
                                        try:
                                            for it in scene.items():
                                                try:
                                                    from PyQt6 import QtWidgets as _qtw

                                                    if isinstance(
                                                        it, _qtw.QGraphicsPixmapItem
                                                    ):
                                                        pix = it.pixmap()
                                                        break
                                                except Exception:
                                                    try:
                                                        if hasattr(it, "pixmap"):
                                                            pix = it.pixmap()
                                                            break
                                                    except Exception:
                                                        pass
                                        except Exception:
                                            pix = None

                                    if pix is None:
                                        return

                                    # write pix to temp file
                                    tmp_path = None
                                    try:
                                        tmp = tempfile.NamedTemporaryFile(
                                            delete=False, suffix=".jpg"
                                        )
                                        tmp_path = tmp.name
                                        tmp.close()
                                        try:
                                            pix.save(tmp_path, "JPG")
                                        except Exception:
                                            try:
                                                qm = pix.toImage()
                                                qm.save(tmp_path, "JPG")
                                            except Exception:
                                                pass
                                    except Exception:
                                        tmp_path = None

                                    if tmp_path is None:
                                        return

                                    # show overlay/spinner
                                    ov = ensure_overlay_for_view(cam_view)
                                    try:
                                        if ov is not None:
                                            try:
                                                if (
                                                    getattr(ov, "_spinner", None)
                                                    is not None
                                                ):
                                                    try:
                                                        ov._spinner.start()
                                                    except Exception:
                                                        pass
                                            except Exception:
                                                pass
                                            ov.show()
                                    except Exception:
                                        pass

                                    # reuse streaming inference path (notifier + thread)
                                    try:
                                        setattr(camera_page, "_inference_running", True)
                                        notifier = _StreamNotifier()
                                        notifier.finished.connect(
                                            lambda res, p: (
                                                _handle_stream_inference_result(res, p),
                                                setattr(
                                                    camera_page,
                                                    "_inference_running",
                                                    False,
                                                ),
                                                # hide spinner/overlay if present
                                                (
                                                    ov._spinner.stop()
                                                    if getattr(ov, "_spinner", None)
                                                    is not None
                                                    else None
                                                ),
                                                (ov.hide() if ov is not None else None),
                                            )
                                        )
                                        Thread(
                                            target=_run_inference_thread,
                                            args=(tmp_path, notifier),
                                            daemon=True,
                                        ).start()
                                    except Exception:
                                        try:
                                            if tmp_path and os.path.exists(tmp_path):
                                                os.remove(tmp_path)
                                        except Exception:
                                            pass
                                        setattr(
                                            camera_page, "_inference_running", False
                                        )
                                except Exception:
                                    pass
                            except Exception:
                                pass

                        model_combo.currentIndexChanged.connect(_on_model_changed)
                    except Exception:
                        pass
            except Exception:
                pass
            # replace designer QGraphicsView with ZoomableGraphicsView at runtime
            try:
                from mpcamera.ui.zoomable_view import ZoomableGraphicsView

                if cam_view is not None and not isinstance(
                    cam_view, ZoomableGraphicsView
                ):
                    try:
                        parent = cam_view.parentWidget()
                        layout = None
                        if parent is not None:
                            layout = parent.layout()
                        # create replacement view and copy objectName so findChild still works
                        new_view = ZoomableGraphicsView(parent)
                        try:
                            new_view.setObjectName(cam_view.objectName())
                        except Exception:
                            pass
                        # copy sizePolicy and minimum/maximum sizes
                        try:
                            new_view.setSizePolicy(cam_view.sizePolicy())
                            new_view.setMinimumSize(cam_view.minimumSize())
                            new_view.setMaximumSize(cam_view.maximumSize())
                        except Exception:
                            pass
                        # replace widget in layout if possible
                        replaced = False
                        if layout is not None:
                            for i in range(layout.count()):
                                try:
                                    it = layout.itemAt(i)
                                    if it and it.widget() is cam_view:
                                        layout.removeWidget(cam_view)
                                        cam_view.setParent(None)
                                        layout.insertWidget(i, new_view)
                                        replaced = True
                                        break
                                except Exception:
                                    pass
                        if not replaced and parent is not None:
                            # fallback: reparent into same parent
                            cam_view.setParent(None)
                            new_view.setParent(parent)
                        cam_view = new_view
                    except Exception:
                        pass
            except Exception:
                pass

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

                    # Update button states after showing an image so
                    # clear/upload/capture buttons reflect the new scene.
                    try:
                        # `update_buttons` is defined later in this scope but
                        # will be available by the time this function is invoked.
                        update_buttons()
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
                                            # collect overlay mapping (index -> raw_key) from scene so we can assign stable keys
                                            overlay_index_map = {}
                                            try:
                                                if (
                                                    cam_view is not None
                                                    and cam_view.scene() is not None
                                                ):
                                                    for it_overlay in list(
                                                        cam_view.scene().items()
                                                    ):
                                                        try:
                                                            if (
                                                                it_overlay.data(0)
                                                                == "inference_overlay"
                                                            ):
                                                                try:
                                                                    idx = (
                                                                        it_overlay.data(
                                                                            2
                                                                        )
                                                                    )
                                                                    key = (
                                                                        it_overlay.data(
                                                                            1
                                                                        )
                                                                    )
                                                                    if idx is not None:
                                                                        try:
                                                                            overlay_index_map[
                                                                                int(idx)
                                                                            ] = key
                                                                        except (
                                                                            Exception
                                                                        ):
                                                                            overlay_index_map[
                                                                                idx
                                                                            ] = key
                                                                except Exception:
                                                                    pass
                                                        except Exception:
                                                            pass
                                            except Exception:
                                                overlay_index_map = {}

                                            try:
                                                inf_table.setSortingEnabled(False)
                                            except Exception:
                                                pass
                                            inf_table.setRowCount(0)
                                            for p in preds:
                                                r = inf_table.rowCount()
                                                inf_table.insertRow(r)
                                                # Shape
                                                try:
                                                    # create label item and attach a stable raw_key (prefer overlay index mapping)
                                                    label_item = (
                                                        QtWidgets.QTableWidgetItem(
                                                            str(p.get("label") or "")
                                                        )
                                                    )
                                                    try:
                                                        # prefer to use overlay_index_map if available
                                                        assigned_key = None
                                                        try:
                                                            assigned_key = (
                                                                overlay_index_map.get(r)
                                                            )
                                                        except Exception:
                                                            assigned_key = None
                                                        if assigned_key is None:
                                                            # fallback to deriving raw_key from the prediction dict
                                                            try:
                                                                assigned_key = p.get(
                                                                    "detection_id"
                                                                ) or p.get("id")
                                                            except Exception:
                                                                assigned_key = None
                                                        if assigned_key is None:
                                                            try:
                                                                assigned_key = (
                                                                    json.dumps(
                                                                        p,
                                                                        sort_keys=True,
                                                                        default=str,
                                                                    )
                                                                )
                                                            except Exception:
                                                                assigned_key = str(p)
                                                        try:
                                                            label_item.setData(
                                                                QtCore.Qt.ItemDataRole.UserRole,
                                                                assigned_key,
                                                            )
                                                        except Exception:
                                                            pass
                                                    except Exception:
                                                        pass
                                                    inf_table.setItem(r, 0, label_item)
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
                                                # Note: UI no longer has a separate Size column
                                                # (area is now at column 3). Skip any size placeholder.
                                                # Morphometrics: Area, Perimeter, Major/Minor axes, ECD, Skeleton
                                                try:
                                                    # determine image pixel dimensions
                                                    P_width = None
                                                    P_height = None
                                                    try:
                                                        pix_item = None
                                                        for it in (
                                                            scene.items()
                                                            if scene is not None
                                                            else []
                                                        ):
                                                            try:
                                                                from PyQt6 import (
                                                                    QtWidgets as _qtw,
                                                                )

                                                                if isinstance(
                                                                    it,
                                                                    _qtw.QGraphicsPixmapItem,
                                                                ):
                                                                    pix_item = it
                                                                    break
                                                            except Exception:
                                                                if hasattr(
                                                                    it, "pixmap"
                                                                ):
                                                                    pix_item = it
                                                                    break
                                                        if pix_item is not None:
                                                            try:
                                                                pm = pix_item.pixmap()
                                                                P_width = int(
                                                                    pm.width()
                                                                )
                                                                P_height = int(
                                                                    pm.height()
                                                                )
                                                            except Exception:
                                                                P_width = None
                                                                P_height = None
                                                        if (
                                                            P_width is None
                                                            and img_np is not None
                                                        ):
                                                            try:
                                                                h, w = img_np.shape[:2]
                                                                P_width = int(w)
                                                                P_height = int(h)
                                                            except Exception:
                                                                P_width = None
                                                                P_height = None
                                                    except Exception:
                                                        P_width = None
                                                        P_height = None

                                                    # read magnification from UI spinbox
                                                    try:
                                                        mag_w = camera_page.findChild(
                                                            QtWidgets.QDoubleSpinBox,
                                                            "magnificationSpinbox",
                                                        )
                                                        M_total = (
                                                            float(mag_w.value())
                                                            if mag_w is not None
                                                            else 1.0
                                                        )
                                                    except Exception:
                                                        M_total = 1.0

                                                    # if image dims available, compute μm/pixel
                                                    um_per_px = None
                                                    try:
                                                        if (
                                                            P_width
                                                            and P_height
                                                            and M_total
                                                            and M_total > 0
                                                        ):
                                                            res_um = calculate_micrometers_per_pixel(
                                                                M_total,
                                                                P_width,
                                                                P_height,
                                                            )
                                                            um_per_px = float(
                                                                res_um.get(
                                                                    "average_multiplier_um",
                                                                    0,
                                                                )
                                                            )
                                                    except Exception:
                                                        um_per_px = None

                                                    # extract polygon points (pixels)
                                                    pts = []
                                                    try:
                                                        pts = p.get("points") or []
                                                        if not pts:
                                                            try:
                                                                raw = p.get("raw") or {}
                                                                pts = (
                                                                    extract_points_from_prediction(
                                                                        raw
                                                                    )
                                                                    or []
                                                                )
                                                            except Exception:
                                                                pts = []
                                                    except Exception:
                                                        pts = []

                                                    if (
                                                        pts
                                                        and len(pts) >= 3
                                                        and um_per_px is not None
                                                    ):
                                                        try:
                                                            arr = np.array(
                                                                pts, dtype=float
                                                            )
                                                            # polygon area (px^2) via shoelace
                                                            x = arr[:, 0]
                                                            y = arr[:, 1]
                                                            area_px = 0.5 * abs(
                                                                np.dot(
                                                                    x, np.roll(y, -1)
                                                                )
                                                                - np.dot(
                                                                    y, np.roll(x, -1)
                                                                )
                                                            )
                                                            # perimeter (px)
                                                            diffs = np.diff(
                                                                arr,
                                                                axis=0,
                                                                append=arr[:1],
                                                            )
                                                            seglens = np.hypot(
                                                                diffs[:, 0], diffs[:, 1]
                                                            )
                                                            perim_px = float(
                                                                np.sum(seglens)
                                                            )
                                                            # PCA for major/minor axis lengths (px)
                                                            try:
                                                                c = arr.mean(axis=0)
                                                                pts_centered = arr - c
                                                                cov = np.cov(
                                                                    pts_centered.T
                                                                )
                                                                evals, evecs = (
                                                                    np.linalg.eigh(cov)
                                                                )
                                                                # sort descending
                                                                order = np.argsort(
                                                                    evals
                                                                )[::-1]
                                                                evecs = evecs[:, order]
                                                                v1 = evecs[:, 0]
                                                                v2 = evecs[:, 1]
                                                                proj1 = (
                                                                    pts_centered.dot(v1)
                                                                )
                                                                proj2 = (
                                                                    pts_centered.dot(v2)
                                                                )
                                                                major_px = float(
                                                                    proj1.max()
                                                                    - proj1.min()
                                                                )
                                                                minor_px = float(
                                                                    proj2.max()
                                                                    - proj2.min()
                                                                )
                                                            except Exception:
                                                                major_px = 0.0
                                                                minor_px = 0.0

                                                            # convert to μm using morphometrics helpers
                                                            try:
                                                                A_um2 = (
                                                                    calculate_area_um2(
                                                                        area_px,
                                                                        um_per_px,
                                                                    )
                                                                )
                                                            except Exception:
                                                                A_um2 = None
                                                            try:
                                                                P_um = calculate_perimeter_um(
                                                                    perim_px, um_per_px
                                                                )
                                                            except Exception:
                                                                P_um = None
                                                            try:
                                                                Lmaj_um = calculate_major_axis_um(
                                                                    major_px, um_per_px
                                                                )
                                                            except Exception:
                                                                Lmaj_um = None
                                                            try:
                                                                Lmin_um = calculate_minor_axis_um(
                                                                    minor_px, um_per_px
                                                                )
                                                            except Exception:
                                                                Lmin_um = None
                                                            try:
                                                                Deq = calculate_equivalent_circular_diameter(
                                                                    (
                                                                        A_um2
                                                                        if A_um2
                                                                        is not None
                                                                        else 0.0
                                                                    ),
                                                                    um_per_px,
                                                                )
                                                            except Exception:
                                                                Deq = None
                                                            try:
                                                                Lsk_um = calculate_skeleton_length_um(
                                                                    major_px, um_per_px
                                                                )
                                                            except Exception:
                                                                Lsk_um = None

                                                            # set table cells (columns: 3..8)
                                                            try:
                                                                inf_table.setItem(
                                                                    r,
                                                                    3,
                                                                    QtWidgets.QTableWidgetItem(
                                                                        f"{A_um2:.2f}"
                                                                        if A_um2
                                                                        is not None
                                                                        else ""
                                                                    ),
                                                                )
                                                            except Exception:
                                                                pass
                                                            try:
                                                                inf_table.setItem(
                                                                    r,
                                                                    4,
                                                                    QtWidgets.QTableWidgetItem(
                                                                        f"{P_um:.2f}"
                                                                        if P_um
                                                                        is not None
                                                                        else ""
                                                                    ),
                                                                )
                                                            except Exception:
                                                                pass
                                                            try:
                                                                inf_table.setItem(
                                                                    r,
                                                                    5,
                                                                    QtWidgets.QTableWidgetItem(
                                                                        f"{Lmaj_um:.2f}"
                                                                        if Lmaj_um
                                                                        is not None
                                                                        else ""
                                                                    ),
                                                                )
                                                            except Exception:
                                                                pass
                                                            try:
                                                                inf_table.setItem(
                                                                    r,
                                                                    6,
                                                                    QtWidgets.QTableWidgetItem(
                                                                        f"{Lmin_um:.2f}"
                                                                        if Lmin_um
                                                                        is not None
                                                                        else ""
                                                                    ),
                                                                )
                                                            except Exception:
                                                                pass
                                                            try:
                                                                inf_table.setItem(
                                                                    r,
                                                                    7,
                                                                    QtWidgets.QTableWidgetItem(
                                                                        f"{Deq:.2f}"
                                                                        if Deq
                                                                        is not None
                                                                        else ""
                                                                    ),
                                                                )
                                                            except Exception:
                                                                pass
                                                            try:
                                                                inf_table.setItem(
                                                                    r,
                                                                    8,
                                                                    QtWidgets.QTableWidgetItem(
                                                                        f"{Lsk_um:.2f}"
                                                                        if Lsk_um
                                                                        is not None
                                                                        else ""
                                                                    ),
                                                                )
                                                            except Exception:
                                                                pass
                                                        except Exception:
                                                            pass
                                                    else:
                                                        # if no polygon or missing um conversion, leave blank
                                                        pass
                                                except Exception:
                                                    pass
                                    except Exception:
                                        pass

                                    # connect selection handler: selecting a row isolates its overlay(s)
                                    try:
                                        if not getattr(
                                            inf_table,
                                            "_overlay_selection_connected",
                                            False,
                                        ):

                                            def _on_inf_selection_changed(
                                                selected, deselected
                                            ):
                                                try:
                                                    sel_idxs = (
                                                        inf_table.selectionModel().selectedRows()
                                                    )
                                                    # fallback for cell-selection tables: collect selected items' rows
                                                    if not sel_idxs:
                                                        try:
                                                            items = (
                                                                inf_table.selectedItems()
                                                            )
                                                            rows = sorted(
                                                                {
                                                                    it.row()
                                                                    for it in items
                                                                }
                                                            )
                                                            sel_idxs = [
                                                                inf_table.model().index(
                                                                    r, 0
                                                                )
                                                                for r in rows
                                                            ]
                                                        except Exception:
                                                            sel_idxs = []
                                                    selected_keys = set()
                                                    for idx in sel_idxs:
                                                        try:
                                                            it = inf_table.item(
                                                                idx.row(), 0
                                                            )
                                                            if it is not None:
                                                                k = it.data(
                                                                    QtCore.Qt.ItemDataRole.UserRole
                                                                )
                                                                if k is not None:
                                                                    selected_keys.add(k)
                                                        except Exception:
                                                            pass
                                                    scene = (
                                                        cam_view.scene()
                                                        if cam_view is not None
                                                        else None
                                                    )
                                                    if scene is None:
                                                        return
                                                    show_all = len(selected_keys) == 0
                                                    for it in list(scene.items()):
                                                        try:
                                                            if (
                                                                it.data(0)
                                                                == "inference_overlay"
                                                            ):
                                                                if show_all:
                                                                    it.setVisible(True)
                                                                else:
                                                                    try:
                                                                        item_key = (
                                                                            it.data(1)
                                                                        )
                                                                        it.setVisible(
                                                                            item_key
                                                                            in selected_keys
                                                                        )
                                                                    except Exception:
                                                                        it.setVisible(
                                                                            False
                                                                        )
                                                        except Exception:
                                                            pass
                                                except Exception:
                                                    pass
                                                try:
                                                    # write a small debug record for selection actions
                                                    dbg_path = (
                                                        pathlib.Path(__file__)
                                                        .resolve()
                                                        .parents[1]
                                                        / "prediction_debug.txt"
                                                    )
                                                    try:
                                                        with open(
                                                            dbg_path,
                                                            "a",
                                                            encoding="utf-8",
                                                        ) as _dbg:
                                                            _dbg.write(
                                                                "--- SELECTION_CHANGED ---\n"
                                                            )
                                                            _dbg.write(
                                                                f"selected_keys: {list(selected_keys)}\n"
                                                            )
                                                            _dbg.write(
                                                                f"show_all: {show_all}\n"
                                                            )
                                                    except Exception:
                                                        pass
                                                except Exception:
                                                    pass

                                            try:
                                                inf_table.selectionModel().selectionChanged.connect(
                                                    _on_inf_selection_changed
                                                )
                                                setattr(
                                                    inf_table,
                                                    "_overlay_selection_connected",
                                                    True,
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
            # --- Camera control, capture, and clearing logic ---
            try:
                cam_btn = camera_page.findChild(
                    QtWidgets.QPushButton, "cameraControlButton"
                )
                cap_btn = camera_page.findChild(QtWidgets.QPushButton, "captureButton")
                clear_btn = camera_page.findChild(
                    QtWidgets.QPushButton, "clearImgButton"
                )

                # internal state on the camera_page widget
                # _vc: cv2.VideoCapture or None
                # _frame_timer: QTimer for grabbing frames
                # _streaming: bool
                # _pause_updates: bool (when a capture has frozen the view)
                setattr(camera_page, "_vc", None)
                setattr(camera_page, "_frame_timer", None)
                setattr(camera_page, "_streaming", False)
                setattr(camera_page, "_pause_updates", False)

                # Ensure interactive controls show a pointing-hand cursor
                try:
                    hand = QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor)
                    widgets_to_cursor = [
                        cam_btn,
                        cap_btn,
                        clear_btn,
                        img_btn,
                        camera_page.findChild(
                            QtWidgets.QPushButton, "saveResultButton"
                        ),
                        camera_page.findChild(QtWidgets.QComboBox, "sourceCombo"),
                        camera_page.findChild(QtWidgets.QComboBox, "sourceCombo_2"),
                        # include model selection combo if present
                        model_combo,
                        farm_combo,
                        soil_combo,
                        camera_page.findChild(QtWidgets.QTableWidget, "inferenceTable"),
                    ]
                    for w in widgets_to_cursor:
                        try:
                            if w is not None:
                                w.setCursor(hand)
                        except Exception:
                            pass
                except Exception:
                    pass

                def update_buttons():
                    streaming = getattr(camera_page, "_streaming", False)
                    paused = getattr(camera_page, "_pause_updates", False)
                    # has image in view?
                    has_scene = False
                    try:
                        has_scene = (
                            cam_view is not None
                            and cam_view.scene() is not None
                            and len(cam_view.scene().items()) > 0
                        )
                    except Exception:
                        has_scene = False

                    # clearImgButton: enabled only when there is an image and camera not streaming
                    try:
                        if clear_btn is not None:
                            clear_btn.setEnabled((not streaming) and has_scene)
                    except Exception:
                        pass

                    # imgUploadButton: disabled while streaming
                    try:
                        if img_btn is not None:
                            img_btn.setEnabled(not streaming)
                    except Exception:
                        pass

                    # captureButton: enabled only during active camera stream
                    try:
                        if cap_btn is not None:
                            cap_btn.setEnabled(bool(streaming))
                            # update capture button label depending on paused state
                            if streaming and getattr(
                                camera_page, "_pause_updates", False
                            ):
                                cap_btn.setText("Resume Capture")
                            elif streaming:
                                cap_btn.setText("Freeze Capture")
                            else:
                                # default label when not streaming
                                cap_btn.setText("Capture Frame")
                    except Exception:
                        pass

                    # cameraControlButton text update
                    try:
                        if cam_btn is not None:
                            try:
                                if streaming:
                                    cam_btn.setText("Stop Camera")
                                else:
                                    cam_btn.setText("Start Camera")
                            except Exception:
                                pass
                    except Exception:
                        pass

                def _show_pixmap_in_view(pix: QtGui.QPixmap):
                    try:
                        if cam_view is None:
                            return
                        # try to reuse existing scene and pixmap item so overlays stay on top
                        scene = cam_view.scene()
                        pix_item = None
                        if scene is not None:
                            try:
                                for it in scene.items():
                                    try:
                                        from PyQt6 import QtWidgets as _qtw

                                        if isinstance(it, _qtw.QGraphicsPixmapItem):
                                            pix_item = it
                                            break
                                    except Exception:
                                        if hasattr(it, "pixmap"):
                                            pix_item = it
                                            break
                            except Exception:
                                pix_item = None

                        if scene is None:
                            scene = QtWidgets.QGraphicsScene()
                            pix_item = scene.addPixmap(pix)
                            cam_view.setScene(scene)
                        else:
                            if pix_item is None:
                                try:
                                    pix_item = scene.addPixmap(pix)
                                except Exception:
                                    scene.clear()
                                    pix_item = scene.addPixmap(pix)
                            else:
                                try:
                                    pix_item.setPixmap(pix)
                                except Exception:
                                    try:
                                        scene.removeItem(pix_item)
                                    except Exception:
                                        pass
                                    pix_item = scene.addPixmap(pix)

                        cam_view.setRenderHints(
                            QtGui.QPainter.RenderHint.SmoothPixmapTransform
                            | QtGui.QPainter.RenderHint.Antialiasing
                        )
                        try:
                            rect = (
                                pix_item.boundingRect()
                                if pix_item is not None
                                else scene.itemsBoundingRect()
                            )
                            cam_view.fitInView(
                                rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio
                            )
                        except Exception:
                            pass
                    except Exception:
                        pass

                def _grab_frame_and_show():
                    try:
                        vc = getattr(camera_page, "_vc", None)
                        if vc is None:
                            return
                        ok, frame = vc.read()
                        if not ok or frame is None:
                            return
                        # convert BGR -> RGB
                        try:
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        except Exception:
                            frame_rgb = frame[:, :, ::-1]
                        h, w = frame_rgb.shape[:2]
                        bytes_per_line = 3 * w
                        qimg = QtGui.QImage(
                            frame_rgb.data,
                            w,
                            h,
                            bytes_per_line,
                            QtGui.QImage.Format.Format_RGB888,
                        )
                        pix = QtGui.QPixmap.fromImage(qimg)
                        # store last frame
                        try:
                            setattr(camera_page, "_last_pixmap", pix)
                        except Exception:
                            pass
                        # only update view when not paused
                        if not getattr(camera_page, "_pause_updates", False):
                            _show_pixmap_in_view(pix)
                    except Exception:
                        pass

                # --- Streaming inference support ---
                # avoid overlapping inference runs
                setattr(camera_page, "_inference_running", False)
                setattr(camera_page, "_inference_timer", None)

                def _handle_stream_inference_result(result, tmp_path=None):
                    try:
                        # remove temporary file
                        try:
                            if tmp_path and os.path.exists(tmp_path):
                                os.remove(tmp_path)
                        except Exception:
                            pass

                        # If there's no view or scene, nothing to render
                        scene = cam_view.scene() if cam_view is not None else None
                        if scene is None:
                            return

                        # draw overlays
                        try:
                            render_predictions_on_scene(scene, result)
                        except Exception:
                            pass

                        # update inference table and counters using existing logic
                        try:
                            preds = parse_result_to_preds(result)
                        except Exception:
                            preds = []

                        try:
                            inf_table = camera_page.findChild(
                                QtWidgets.QTableWidget, "inferenceTable"
                            )
                            if inf_table is not None:
                                inf_table.setRowCount(0)
                                # re-use some of the logic used for uploaded images
                                for p in preds:
                                    r = inf_table.rowCount()
                                    inf_table.insertRow(r)
                                    try:
                                        label_item = QtWidgets.QTableWidgetItem(
                                            str(p.get("label") or "")
                                        )
                                        assigned_key = None
                                        try:
                                            assigned_key = p.get(
                                                "detection_id"
                                            ) or p.get("id")
                                        except Exception:
                                            assigned_key = None
                                        if assigned_key is None:
                                            try:
                                                assigned_key = json.dumps(
                                                    p, sort_keys=True, default=str
                                                )
                                            except Exception:
                                                assigned_key = str(p)
                                        try:
                                            label_item.setData(
                                                QtCore.Qt.ItemDataRole.UserRole,
                                                assigned_key,
                                            )
                                        except Exception:
                                            pass
                                        inf_table.setItem(r, 0, label_item)
                                    except Exception:
                                        pass
                                    try:
                                        sc = p.get("score")
                                        sc_text = (
                                            f"{float(sc):.2f}" if sc is not None else ""
                                        )
                                        inf_table.setItem(
                                            r, 1, QtWidgets.QTableWidgetItem(sc_text)
                                        )
                                    except Exception:
                                        pass
                                    try:
                                        inf_table.setItem(
                                            r, 2, QtWidgets.QTableWidgetItem("")
                                        )
                                    except Exception:
                                        pass
                                    # Size column removed from UI; do not write placeholder
                                    # Morphometrics for streaming results (same approach as uploaded image)
                                    try:
                                        # determine image pixel dimensions
                                        P_width = None
                                        P_height = None
                                        try:
                                            pix_item = None
                                            for it in (
                                                scene.items()
                                                if scene is not None
                                                else []
                                            ):
                                                try:
                                                    from PyQt6 import QtWidgets as _qtw

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
                                                try:
                                                    pm = pix_item.pixmap()
                                                    P_width = int(pm.width())
                                                    P_height = int(pm.height())
                                                except Exception:
                                                    P_width = None
                                                    P_height = None
                                            if P_width is None:
                                                pix = getattr(
                                                    camera_page, "_last_pixmap", None
                                                )
                                                if pix is not None:
                                                    try:
                                                        P_width = int(pix.width())
                                                        P_height = int(pix.height())
                                                    except Exception:
                                                        P_width = None
                                                        P_height = None
                                        except Exception:
                                            P_width = None
                                            P_height = None

                                        # magnification
                                        try:
                                            mag_w = camera_page.findChild(
                                                QtWidgets.QDoubleSpinBox,
                                                "magnificationSpinbox",
                                            )
                                            M_total = (
                                                float(mag_w.value())
                                                if mag_w is not None
                                                else 1.0
                                            )
                                        except Exception:
                                            M_total = 1.0

                                        um_per_px = None
                                        try:
                                            if (
                                                P_width
                                                and P_height
                                                and M_total
                                                and M_total > 0
                                            ):
                                                res_um = (
                                                    calculate_micrometers_per_pixel(
                                                        M_total, P_width, P_height
                                                    )
                                                )
                                                um_per_px = float(
                                                    res_um.get(
                                                        "average_multiplier_um", 0
                                                    )
                                                )
                                        except Exception:
                                            um_per_px = None

                                        # points
                                        pts = []
                                        try:
                                            pts = p.get("points") or []
                                            if not pts:
                                                try:
                                                    raw = p.get("raw") or {}
                                                    pts = (
                                                        extract_points_from_prediction(
                                                            raw
                                                        )
                                                        or []
                                                    )
                                                except Exception:
                                                    pts = []
                                        except Exception:
                                            pts = []

                                        if (
                                            pts
                                            and len(pts) >= 3
                                            and um_per_px is not None
                                        ):
                                            try:
                                                arr = np.array(pts, dtype=float)
                                                x = arr[:, 0]
                                                y = arr[:, 1]
                                                area_px = 0.5 * abs(
                                                    np.dot(x, np.roll(y, -1))
                                                    - np.dot(y, np.roll(x, -1))
                                                )
                                                diffs = np.diff(
                                                    arr, axis=0, append=arr[:1]
                                                )
                                                seglens = np.hypot(
                                                    diffs[:, 0], diffs[:, 1]
                                                )
                                                perim_px = float(np.sum(seglens))
                                                try:
                                                    c = arr.mean(axis=0)
                                                    pts_centered = arr - c
                                                    cov = np.cov(pts_centered.T)
                                                    evals, evecs = np.linalg.eigh(cov)
                                                    order = np.argsort(evals)[::-1]
                                                    evecs = evecs[:, order]
                                                    v1 = evecs[:, 0]
                                                    v2 = evecs[:, 1]
                                                    proj1 = pts_centered.dot(v1)
                                                    proj2 = pts_centered.dot(v2)
                                                    major_px = float(
                                                        proj1.max() - proj1.min()
                                                    )
                                                    minor_px = float(
                                                        proj2.max() - proj2.min()
                                                    )
                                                except Exception:
                                                    major_px = 0.0
                                                    minor_px = 0.0

                                                try:
                                                    A_um2 = calculate_area_um2(
                                                        area_px, um_per_px
                                                    )
                                                except Exception:
                                                    A_um2 = None
                                                try:
                                                    P_um = calculate_perimeter_um(
                                                        perim_px, um_per_px
                                                    )
                                                except Exception:
                                                    P_um = None
                                                try:
                                                    Lmaj_um = calculate_major_axis_um(
                                                        major_px, um_per_px
                                                    )
                                                except Exception:
                                                    Lmaj_um = None
                                                try:
                                                    Lmin_um = calculate_minor_axis_um(
                                                        minor_px, um_per_px
                                                    )
                                                except Exception:
                                                    Lmin_um = None
                                                try:
                                                    Deq = calculate_equivalent_circular_diameter(
                                                        (
                                                            A_um2
                                                            if A_um2 is not None
                                                            else 0.0
                                                        ),
                                                        um_per_px,
                                                    )
                                                except Exception:
                                                    Deq = None
                                                try:
                                                    Lsk_um = (
                                                        calculate_skeleton_length_um(
                                                            major_px, um_per_px
                                                        )
                                                    )
                                                except Exception:
                                                    Lsk_um = None

                                                try:
                                                    inf_table.setItem(
                                                        r,
                                                        3,
                                                        QtWidgets.QTableWidgetItem(
                                                            f"{A_um2:.2f}"
                                                            if A_um2 is not None
                                                            else ""
                                                        ),
                                                    )
                                                except Exception:
                                                    pass
                                                try:
                                                    inf_table.setItem(
                                                        r,
                                                        4,
                                                        QtWidgets.QTableWidgetItem(
                                                            f"{P_um:.2f}"
                                                            if P_um is not None
                                                            else ""
                                                        ),
                                                    )
                                                except Exception:
                                                    pass
                                                try:
                                                    inf_table.setItem(
                                                        r,
                                                        5,
                                                        QtWidgets.QTableWidgetItem(
                                                            f"{Lmaj_um:.2f}"
                                                            if Lmaj_um is not None
                                                            else ""
                                                        ),
                                                    )
                                                except Exception:
                                                    pass
                                                try:
                                                    inf_table.setItem(
                                                        r,
                                                        6,
                                                        QtWidgets.QTableWidgetItem(
                                                            f"{Lmin_um:.2f}"
                                                            if Lmin_um is not None
                                                            else ""
                                                        ),
                                                    )
                                                except Exception:
                                                    pass
                                                try:
                                                    inf_table.setItem(
                                                        r,
                                                        7,
                                                        QtWidgets.QTableWidgetItem(
                                                            f"{Deq:.2f}"
                                                            if Deq is not None
                                                            else ""
                                                        ),
                                                    )
                                                except Exception:
                                                    pass
                                                try:
                                                    inf_table.setItem(
                                                        r,
                                                        8,
                                                        QtWidgets.QTableWidgetItem(
                                                            f"{Lsk_um:.2f}"
                                                            if Lsk_um is not None
                                                            else ""
                                                        ),
                                                    )
                                                except Exception:
                                                    pass
                                            except Exception:
                                                pass
                                        else:
                                            pass
                                    except Exception:
                                        pass
                        except Exception:
                            pass

                        # aggregates
                        try:
                            ag = compute_aggregates(preds)

                            def _set_lbl(name, val):
                                try:
                                    lbl = camera_page.findChild(QtWidgets.QLabel, name)
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
                            _set_lbl("fragmentsCount", cnts.get("fragment", 0))
                            _set_lbl("sheetsCount", cnts.get("sheet", 0))
                            _set_lbl("fibersCount", cnts.get("fiber", 0))
                            _set_lbl("foamsCount", cnts.get("foam", 0))
                            _set_lbl("filmsCount", cnts.get("film", 0))
                            _set_lbl("beadsCount", cnts.get("bead", 0))
                        except Exception:
                            pass

                    except Exception:
                        pass

                class _StreamNotifier(QtCore.QObject):
                    finished = QtCore.pyqtSignal(object, str)

                def _run_inference_thread(tmp_path, note: _StreamNotifier):
                    res = None
                    try:
                        client = (
                            RoboflowClient.get_default()
                            if RoboflowClient is not None
                            else None
                        )
                        if client is None:
                            res = None
                        else:
                            res = client.run_workflow(tmp_path)
                    except Exception:
                        try:
                            print(
                                "roboflow: inference failed (stream):",
                                traceback.format_exc(),
                            )
                        except Exception:
                            pass
                    finally:
                        try:
                            note.finished.emit(res, tmp_path)
                        except Exception:
                            # fallback: schedule handler on main thread
                            try:
                                QtCore.QTimer.singleShot(
                                    0,
                                    lambda: _handle_stream_inference_result(
                                        res, tmp_path
                                    ),
                                )
                            except Exception:
                                pass

                def _maybe_run_stream_inference():
                    try:
                        if not getattr(camera_page, "_streaming", False):
                            return
                        if getattr(camera_page, "_pause_updates", False):
                            return
                        if getattr(camera_page, "_inference_running", False):
                            return
                        pix = getattr(camera_page, "_last_pixmap", None)
                        if pix is None:
                            return
                        # write pix to temp file
                        try:
                            tmp = tempfile.NamedTemporaryFile(
                                delete=False, suffix=".jpg"
                            )
                            tmp_path = tmp.name
                            tmp.close()
                            # save pixmap
                            try:
                                pix.save(tmp_path, "JPG")
                            except Exception:
                                # fallback: use unique filename and QImage save
                                try:
                                    qm = pix.toImage()
                                    qm.save(tmp_path, "JPG")
                                except Exception:
                                    pass
                        except Exception:
                            tmp_path = None
                        if tmp_path is None:
                            return
                        # run inference in background
                        try:
                            setattr(camera_page, "_inference_running", True)
                            notifier = _StreamNotifier()
                            notifier.finished.connect(
                                lambda res, p: (
                                    _handle_stream_inference_result(res, p),
                                    setattr(camera_page, "_inference_running", False),
                                )
                            )
                            Thread(
                                target=_run_inference_thread,
                                args=(tmp_path, notifier),
                                daemon=True,
                            ).start()
                        except Exception:
                            try:
                                if tmp_path and os.path.exists(tmp_path):
                                    os.remove(tmp_path)
                            except Exception:
                                pass
                            setattr(camera_page, "_inference_running", False)
                    except Exception:
                        pass

                def start_camera():
                    try:
                        if getattr(camera_page, "_streaming", False):
                            return
                        # try to open default webcam
                        try:
                            vc = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                        except Exception:
                            try:
                                vc = cv2.VideoCapture(0)
                            except Exception:
                                vc = None
                        if vc is None or not getattr(vc, "isOpened", lambda: False)():
                            try:
                                if vc is not None:
                                    vc.release()
                            except Exception:
                                pass
                            print("camera_page: failed to open webcam")
                            return
                        setattr(camera_page, "_vc", vc)
                        # timer for grabbing frames
                        timer = QtCore.QTimer(camera_page)
                        timer.setInterval(33)
                        timer.timeout.connect(_grab_frame_and_show)
                        timer.start()
                        setattr(camera_page, "_frame_timer", timer)
                        setattr(camera_page, "_streaming", True)
                        setattr(camera_page, "_pause_updates", False)
                        update_buttons()
                        # start streaming inference timer at a conservative rate (1s)
                        try:
                            if getattr(camera_page, "_inference_timer", None) is None:
                                inf_timer = QtCore.QTimer(camera_page)
                                inf_timer.setInterval(1000)
                                inf_timer.timeout.connect(_maybe_run_stream_inference)
                                inf_timer.start()
                                setattr(camera_page, "_inference_timer", inf_timer)
                        except Exception:
                            pass
                    except Exception:
                        pass

                def stop_camera():
                    try:
                        # stop timer
                        try:
                            t = getattr(camera_page, "_frame_timer", None)
                            if t is not None:
                                t.stop()
                        except Exception:
                            pass
                        # release capture
                        try:
                            vc = getattr(camera_page, "_vc", None)
                            if vc is not None:
                                try:
                                    vc.release()
                                except Exception:
                                    pass
                                setattr(camera_page, "_vc", None)
                        except Exception:
                            pass
                        # clear the view entirely (no frozen frame)
                        try:
                            if cam_view is not None:
                                cam_view.setScene(QtWidgets.QGraphicsScene())
                        except Exception:
                            pass
                        setattr(camera_page, "_streaming", False)
                        setattr(camera_page, "_pause_updates", False)
                        # stop inference timer and mark not running
                        try:
                            it = getattr(camera_page, "_inference_timer", None)
                            if it is not None:
                                try:
                                    it.stop()
                                except Exception:
                                    pass
                                setattr(camera_page, "_inference_timer", None)
                        except Exception:
                            pass
                        try:
                            setattr(camera_page, "_inference_running", False)
                        except Exception:
                            pass
                        # when stopping the camera completely, also clear overlays and inference state
                        try:
                            # reuse existing clear routine to remove scene, table rows and counters
                            try:
                                clear_image_and_inference()
                            except Exception:
                                # fallback: clear overlays manually
                                if (
                                    cam_view is not None
                                    and cam_view.scene() is not None
                                ):
                                    for it in list(cam_view.scene().items()):
                                        try:
                                            cam_view.scene().removeItem(it)
                                        except Exception:
                                            pass
                        except Exception:
                            pass
                        # update buttons
                        update_buttons()
                    except Exception:
                        pass

                def on_camera_control_clicked():
                    try:
                        if getattr(camera_page, "_streaming", False):
                            stop_camera()
                        else:
                            start_camera()
                    except Exception:
                        pass

                def on_capture_clicked():
                    try:
                        # Only allow capture during streaming
                        if not getattr(camera_page, "_streaming", False):
                            return
                        # toggle pause state
                        paused = getattr(camera_page, "_pause_updates", False)
                        new_paused = not bool(paused)
                        setattr(camera_page, "_pause_updates", new_paused)
                        # if pausing now, ensure last pixmap is stored/shown
                        try:
                            if new_paused:
                                pix = getattr(camera_page, "_last_pixmap", None)
                                if pix is not None and cam_view is not None:
                                    _show_pixmap_in_view(pix)
                            else:
                                # unpaused: let the next timer tick refresh the view
                                pass
                        except Exception:
                            pass
                        update_buttons()
                    except Exception:
                        pass

                def clear_image_and_inference():
                    try:
                        # clear camera view
                        try:
                            if cam_view is not None:
                                cam_view.setScene(QtWidgets.QGraphicsScene())
                        except Exception:
                            pass
                        # clear inference table
                        try:
                            inf_table = camera_page.findChild(
                                QtWidgets.QTableWidget, "inferenceTable"
                            )
                            if inf_table is not None:
                                inf_table.setRowCount(0)
                        except Exception:
                            pass
                        # clear inference cards / counters
                        try:
                            labels = [
                                "totalCount",
                                "aveConfidence",
                                "fragmentsCount",
                                "sheetsCount",
                                "fibersCount",
                                "foamsCount",
                                "filmsCount",
                                "beadsCount",
                            ]
                            for name in labels:
                                try:
                                    lbl = camera_page.findChild(QtWidgets.QLabel, name)
                                    if lbl is not None:
                                        lbl.setText("")
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        # reset captured/paused state
                        setattr(camera_page, "_pause_updates", False)
                        setattr(camera_page, "_last_pixmap", None)
                        update_buttons()
                    except Exception:
                        pass

                # wire buttons
                try:
                    if cam_btn is not None:
                        cam_btn.clicked.connect(on_camera_control_clicked)
                except Exception:
                    pass
                try:
                    if cap_btn is not None:
                        cap_btn.clicked.connect(on_capture_clicked)
                except Exception:
                    pass
                try:
                    if clear_btn is not None:
                        clear_btn.clicked.connect(clear_image_and_inference)
                except Exception:
                    pass

                # initialize button states based on not-streaming
                update_buttons()
            except Exception as e:
                print("camera_page: error wiring camera controls:", e)
        except Exception as e:
            print("camera_page: error wiring image upload:", e)

    except Exception as e:
        print("camera_page.setup failed:", e)
