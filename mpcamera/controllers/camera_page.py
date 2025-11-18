from PyQt6 import QtWidgets, QtCore, QtGui
from threading import Thread
import json
import pathlib
import os
import traceback

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
