"""
Utilities for resolving file paths in both development and bundled (PyInstaller) environments.
"""

import sys
import os
from pathlib import Path


def get_base_dir():
    """
    Get the base directory for the application.

    - In development: returns the project root directory
    - In bundled app: returns the PyInstaller data directory (_MEIPASS)
    """
    # Check if running as a bundled PyInstaller app
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS

    # Development mode: return project root
    # __file__ is mpcamera/path_utils.py, so resolve absolute path and go up two levels
    current_file = Path(__file__).resolve()
    # current_file.parent = .../mpcamera
    # current_file.parent.parent = ... (project root)
    return str(current_file.parent.parent)


def get_resource_path(relative_path):
    """
    Get the absolute path to a resource file.
    
    Args:
        relative_path: Path relative to project root (e.g., "mpcamera/layouts/main.ui")
    
    Returns:
        Absolute path to the resource
    
    Example:
        ui_path = get_resource_path("mpcamera/layouts/cameraPage.ui")
    """
    base = get_base_dir()
    return os.path.join(base, relative_path)
