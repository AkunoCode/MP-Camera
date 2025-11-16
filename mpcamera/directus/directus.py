"""Simple Directus HTTP client for fetching items used by the app.

Reads `DIRECTUS_API_URL` and `DIRECTUS_BEARER_TOKEN` from the environment by
default (module will call load_dotenv so a local `.env` works during dev).

Provides convenience methods for the three endpoints requested by the user:
- items/sites
- items/soilsamples
- items/microplastics

This module keeps the API surface intentionally small and returns the parsed
JSON response from Directus. It uses `requests` and `python-dotenv`.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

try:
    # load .env in development if present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    load_dotenv = None

logger = logging.getLogger(__name__)


class DirectusClient:
    """Minimal Directus client.

    Example:
        client = DirectusClient()
        sites = client.get_sites(params={"fields": "*"})

    Inputs:
        api_url: base url like https://directus.example.com
        bearer_token: optional Directus API token; if omitted the client will
                      read from the `DIRECTUS_BEARER_TOKEN` env var.

    Methods return the parsed JSON response from Directus.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        bearer_token: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.api_url = api_url or os.environ.get("DIRECTUS_API_URL")
        self.bearer_token = bearer_token or os.environ.get("DIRECTUS_BEARER_TOKEN")
        self.timeout = timeout

        if not self.api_url:
            raise ValueError("DIRECTUS_API_URL is not set (env or api_url argument)")

        self.session = requests.Session()
        # Set sensible headers
        self.session.headers.update({"Accept": "application/json"})
        if self.bearer_token:
            self.session.headers.update(
                {"Authorization": f"Bearer {self.bearer_token}"}
            )
        else:
            logger.debug(
                "No DIRECTUS_BEARER_TOKEN provided; requests will be unauthenticated"
            )

    def _build_url(self, path: str) -> str:
        return f"{self.api_url.rstrip('/')}/{path.lstrip('/')}"

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._build_url(path)
        resp = self.session.get(url, params=params, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            # attach content to the error for easier debugging
            logger.debug("Directus error response: %s", resp.text)
            raise
        # Return parsed JSON; callers expect dict/list depending on Directus
        return resp.json()

    def get_sites(self, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET /items/sites

        params: optional query params passed to Directus (fields, filter, limit, etc.)
        """
        return self._get("items/sites", params=params)

    def get_soilsamples(self, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET /items/soilsamples"""
        return self._get("items/soilsamples", params=params)

    def get_microplastics(self, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET /items/microplastics"""
        return self._get("items/microplastics", params=params)

    def upload_file(self, file_path: str) -> Any:
        """Upload a file to Directus `/files` and return the created file record.

        Returns the parsed JSON response (Directus usually returns {"data": {...}}).
        This helper is useful to upload an image and then use its `id` as the
        `image` field when creating a microplastic.
        """
        url = self._build_url("files")
        # Provide filename and content-type to help Directus detect the file
        # correctly. Use multipart/form-data with a tuple: (filename, fileobj, mime).
        filename = os.path.basename(file_path)
        mime = "image/png"
        try:
            # attempt to infer from extension
            ext = os.path.splitext(filename)[1].lower()
            if ext in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ext == ".bmp":
                mime = "image/bmp"
            elif ext == ".gif":
                mime = "image/gif"
        except Exception:
            pass

        with open(file_path, "rb") as fh:
            files = {"file": (filename, fh, mime)}
            # include title metadata to make the file easier to find in Directus
            data = {"title": filename}
            resp = self.session.post(url, files=files, data=data, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.debug("Directus file upload error: %s", resp.text)
            raise
        return resp.json()

    def create_microplastic(self, item: Dict[str, Any]) -> Any:
        """POST /items/microplastics to create a microplastic record.

        `item` should be a mapping with the collection fields, for example:

            {
                "image": "<file-uuid>",
                "shape": "fiber",
                "color": "red",
                "confidence_level": "high",
                "area_um2": "123",
                ...
            }

        If you need to upload a local image file first, call `upload_file()` and
        pass the returned file id as the `image` value.
        """
        url = self._build_url("items/microplastics")
        resp = self.session.post(url, json=item, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.debug("Directus create_microplastic error: %s", resp.text)
            raise
        return resp.json()

    def create_soilsample(self, item: Dict[str, Any]) -> Any:
        """POST /items/soilsamples to create a soilsample record.

        `item` should contain the soilsample fields, for example:

            {
                "site": 1,                     # integer id of the site (m2o)
                "mass_kg": "0.5",            # string per schema
                "date_collected": "2025-09-13", # ISO date (YYYY-MM-DD)
                "soil_type": "loam",         # one of allowed choices
            }

        Directus accepts dates as ISO strings; adjust formatting if you pass
        datetime.date or datetime objects.
        """
        url = self._build_url("items/soilsamples")
        resp = self.session.post(url, json=item, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.debug("Directus create_soilsample error: %s", resp.text)
            raise
        return resp.json()

    def create_site(self, item: Dict[str, Any]) -> Any:
        """POST /items/sites to create a site record.

        `item` should contain the site fields, for example:

            {
                "site_name": "Farm A",
                "owner": "Alice",
                "longitude": "151.2093",
                "latitude": "-33.8688",
                "crops": ["wheat", "barley"],    # JSON field
                "remarks": "Notes about the site",
                "fiber_count": "10",
                "fragment_count": "4",
                "foam_count": "0",
                "film_count": "1",
                "beads_count": "0",
                "address": "123 Farm Rd",
                "plastic_activity": ["plastic mulching"], # JSON field
                "water_source": ["ground water"],          # JSON field
                "cultivation_practice": "integrated",
                "land_area_ha": "2.5",
            }

        Note: `crops`, `plastic_activity`, and `water_source` are JSON fields
        (use lists or dicts). If you need to upload site photos, upload files
        via `upload_file()` and attach them using the alias/relationship field
        when querying or use Directus file relation patterns as needed.
        """
        url = self._build_url("items/sites")
        resp = self.session.post(url, json=item, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.debug("Directus create_site error: %s", resp.text)
            raise
        return resp.json()

    def _patch(self, path: str, data: Dict[str, Any]) -> Any:
        """Internal helper to PATCH a Directus path and return parsed JSON."""
        url = self._build_url(path)
        resp = self.session.patch(url, json=data, timeout=self.timeout)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.debug("Directus PATCH error for %s: %s", path, resp.text)
            raise
        return resp.json()

    def update_microplastic(self, item_id: Any, data: Dict[str, Any]) -> Any:
        """PATCH /items/microplastics/{id} to update a microplastic record.

        item_id: the id (integer or uuid) of the microplastic to update.
        data: partial or full mapping of fields to update.
        """
        return self._patch(f"items/microplastics/{item_id}", data)

    def update_soilsample(self, item_id: Any, data: Dict[str, Any]) -> Any:
        """PATCH /items/soilsamples/{id} to update a soilsample record."""
        return self._patch(f"items/soilsamples/{item_id}", data)

    def update_site(self, item_id: Any, data: Dict[str, Any]) -> Any:
        """PATCH /items/sites/{id} to update a site record."""
        return self._patch(f"items/sites/{item_id}", data)


__all__ = ["DirectusClient"]
