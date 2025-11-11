"""Directus subpackage exports.

This module makes `DirectusClient` available as `mpcamera.directus.DirectusClient`
so existing import sites don't need to change after moving `directus.py` into
the `directus/` directory.
"""

from .directus import DirectusClient

__all__ = ["DirectusClient"]
