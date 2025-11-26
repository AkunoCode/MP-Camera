import os
import json
import numpy as np
from typing import List, Dict, Any, Optional

# Import your calculation utils here
from mpcamera.utils.um_per_pixel import calculate_micrometers_per_pixel
from mpcamera.utils.morphometrics import (
    calculate_area_um2,
    calculate_perimeter_um,
    calculate_major_axis_um,
    calculate_minor_axis_um,
    calculate_equivalent_circular_diameter,
    calculate_skeleton_length_um,
)
from mpcamera.utils.prediction_utils import extract_points_from_prediction


class ResultsManager:
    """
    Handles the business logic for calculating metrics and uploading data
    to Directus, separating it from the PyQt UI.
    """

    @staticmethod
    def calculate_morphometrics(
        pred: Dict, img_w: int, img_h: int, magnification: float
    ) -> Dict[str, float]:
        """
        Wraps the specific morphometric calculations.
        """
        um_per_px = None
        stats = {
            k: None for k in ["area", "perimeter", "major", "minor", "deq", "skeleton"]
        }

        if img_w and img_h:
            try:
                res = calculate_micrometers_per_pixel(magnification, img_w, img_h)
                um_per_px = float(res.get("average_multiplier_um", 0))
            except Exception:
                pass

        stats["um_per_px"] = um_per_px

        # Extract points
        pts = (
            pred.get("points")
            or extract_points_from_prediction(pred.get("raw") or {})
            or []
        )

        if len(pts) < 3 or not um_per_px:
            return stats

        try:
            arr = np.array(pts, dtype=float)

            # Basic Geometry
            x, y = arr[:, 0], arr[:, 1]
            area_px = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            diffs = np.diff(arr, axis=0, append=arr[:1])
            perim_px = float(np.sum(np.hypot(diffs[:, 0], diffs[:, 1])))

            # PCA for Axis
            pts_c = arr - arr.mean(axis=0)
            evals, evecs = np.linalg.eigh(np.cov(pts_c.T))
            order = np.argsort(evals)[::-1]
            evecs = evecs[:, order]
            proj1 = pts_c.dot(evecs[:, 0])
            proj2 = pts_c.dot(evecs[:, 1])
            major_px = float(proj1.max() - proj1.min())
            minor_px = float(proj2.max() - proj2.min())

            # Conversions
            stats["area"] = calculate_area_um2(area_px, um_per_px)
            stats["perimeter"] = calculate_perimeter_um(perim_px, um_per_px)
            stats["major"] = calculate_major_axis_um(major_px, um_per_px)
            stats["minor"] = calculate_minor_axis_um(minor_px, um_per_px)
            stats["deq"] = calculate_equivalent_circular_diameter(
                stats["area"] or 0, um_per_px
            )
            stats["skeleton"] = calculate_skeleton_length_um(major_px, um_per_px)
        except Exception as e:
            print(f"Morphometric Calc Error: {e}")
            pass

        return stats

    @staticmethod
    def process_upload(
        client, payloads: List[Dict], img_path: Optional[str] = None
    ) -> int:
        """
        Handles the complex logic of uploading the image, linking it to records,
        and updating the aggregate counts on the parent SoilSample and Site.
        Returns the number of records saved.
        """
        count = 0
        img_id = None

        # 1. Upload Image(s)
        # If individual payloads include an internal key `_image_path`, upload
        # each of those and attach the returned file id to that payload. Otherwise
        # fall back to uploading the provided `img_path` once and assigning it to
        # all payloads (backwards compatibility).
        if payloads:
            # Per-payload uploads
            for p in payloads:
                local_path = p.get("_image_path")
                if local_path and os.path.exists(local_path):
                    try:
                        resp = client.upload_file(local_path)
                        if isinstance(resp, dict) and "data" in resp:
                            p["image"] = resp["data"].get("id")
                    except Exception as e:
                        print(f"Image upload failed for {local_path}: {e}")
                    finally:
                        try:
                            os.remove(local_path)
                        except Exception:
                            pass

        # If no per-payload images were uploaded, try the global img_path
        if (
            (not any(p.get("image") for p in payloads))
            and img_path
            and os.path.exists(img_path)
        ):
            try:
                resp = client.upload_file(img_path)
                if isinstance(resp, dict) and "data" in resp:
                    img_id = resp["data"].get("id")
            except Exception as e:
                print(f"Image upload failed: {e}")
            finally:
                try:
                    os.remove(img_path)
                except Exception:
                    pass

        # 2. Prepare Aggregate Counters
        shape_counters = {
            "fiber_count": 0,
            "fragment_count": 0,
            "sheets_count": 0,
            "foam_count": 0,
            "film_count": 0,
            "beads_count": 0,
        }

        def _shape_to_field(shape_label: str) -> Optional[str]:
            if not shape_label:
                return None
            s = str(shape_label).strip().lower()
            if s in ("fiber", "fibers"):
                return "fiber_count"
            if s in ("fragment", "fragments"):
                return "fragment_count"
            if s in ("sheet", "sheets"):
                return "sheets_count"
            if s in ("foam", "foams"):
                return "foam_count"
            if s in ("film", "films"):
                return "film_count"
            if s in ("bead", "beads", "pellet"):
                return "beads_count"
            return None

        # 3. Create Records
        soil_id = payloads[0].get("sample_source") if payloads else None

        for p in payloads:
            try:
                if img_id:
                    p["image"] = img_id
                client.create_microplastic(p)
                count += 1

                # Update counter
                field = _shape_to_field(p.get("shape"))
                if field:
                    shape_counters[field] += 1
            except Exception as e:
                print(f"Failed to create record: {e}")

        # 4. Update Aggregates (Soil & Site)
        if soil_id and any(v > 0 for v in shape_counters.values()):
            ResultsManager._update_aggregates(client, soil_id, shape_counters)

        return count

    @staticmethod
    def _update_aggregates(client, soil_id, shape_counters):
        """Helper to update parent counters recursively."""
        try:
            # Get current soil sample to check existing counts
            soils_resp = client.get_soilsamples()
            # Handle Directus response variations (dict vs list)
            soils = (
                soils_resp.get("data", [])
                if isinstance(soils_resp, dict)
                else soils_resp
            )

            sample = next((s for s in soils if s.get("id") == soil_id), None)
            if not sample:
                return

            # Update Soil Sample
            update_data = {}
            for field, delta in shape_counters.items():
                if delta <= 0:
                    continue
                try:
                    existing = int(sample.get(field) or 0)
                except:
                    existing = 0
                update_data[field] = existing + delta

            if update_data:
                client.update_soilsample(soil_id, update_data)

            # Update Parent Site
            site_id = None
            for rel in ("site", "site_id", "farm"):
                if rel in sample:
                    site_id = sample.get(rel)
                    break

            if site_id:
                sites_resp = client.get_sites()
                sites = (
                    sites_resp.get("data", [])
                    if isinstance(sites_resp, dict)
                    else sites_resp
                )
                site = next((s for s in sites if s.get("id") == site_id), None)

                if site:
                    site_update = {}
                    for field, delta in shape_counters.items():
                        if delta <= 0:
                            continue
                        try:
                            existing = int(site.get(field) or 0)
                        except:
                            existing = 0
                        site_update[field] = existing + delta

                    if site_update:
                        client.update_site(site_id, site_update)

        except Exception as e:
            print(f"Aggregate update failed: {e}")
