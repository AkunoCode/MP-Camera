from PyQt6 import QtWidgets
from mpcamera.utils.camera_utils import get_site_id_from_sample


class FormHandler:
    """Manages the Farm and Soil dropdown interactions."""

    def __init__(
        self, farm_combo: QtWidgets.QComboBox, soil_combo: QtWidgets.QComboBox
    ):
        self.farm_combo = farm_combo
        self.soil_combo = soil_combo
        self._cached_soils = []

        # Wire signals internally
        if self.farm_combo:
            self.farm_combo.currentIndexChanged.connect(self._on_farm_changed)
        if self.soil_combo:
            self.soil_combo.currentIndexChanged.connect(self._on_soil_changed)

    def populate(self, sites, soils):
        self._cached_soils = soils or []
        self._update_farm_combo(sites)

        current_farm = self.farm_combo.currentData() if self.farm_combo else None
        self._filter_soil_combo(current_farm)

    def get_selected_soil_id(self):
        if self.soil_combo:
            return self.soil_combo.currentData()
        return None

    def _update_farm_combo(self, sites):
        if not self.farm_combo:
            return
        self.farm_combo.blockSignals(True)
        self.farm_combo.clear()
        for item in sites:
            name = item.get("site_name") or item.get("name") or str(item.get("id"))
            self.farm_combo.addItem(str(name), item.get("id"))
        self.farm_combo.setCurrentIndex(-1)
        self.farm_combo.blockSignals(False)

    def _filter_soil_combo(self, site_id):
        if not self.soil_combo:
            return
        self.soil_combo.blockSignals(True)
        self.soil_combo.clear()
        for item in self._cached_soils:
            s_site = get_site_id_from_sample(item)
            if site_id is None or site_id == s_site:
                sid = item.get("id")
                date = item.get("date_collected") or item.get("date") or ""
                self.soil_combo.addItem(f"Sample ID {sid} ({date})", sid)
        self.soil_combo.blockSignals(False)

    def _on_farm_changed(self):
        if self.farm_combo:
            site_id = self.farm_combo.currentData()
            self._filter_soil_combo(site_id)

    def _on_soil_changed(self):
        # Reverse lookup: If user picks a soil, auto-select the farm
        sid = self.soil_combo.currentData() if self.soil_combo else None
        if not sid:
            return
        match = next((i for i in self._cached_soils if i.get("id") == sid), None)
        if match and self.farm_combo:
            site_id = get_site_id_from_sample(match)
            if site_id:
                idx = self.farm_combo.findData(site_id)
                if idx != -1:
                    self.farm_combo.blockSignals(True)
                    self.farm_combo.setCurrentIndex(idx)
                    self.farm_combo.blockSignals(False)
