#!/usr/bin/env python3
"""Validate PyQt6 .ui files for SoilSight conventions."""

import sys
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

LAYOUTS_DIR = Path("mpcamera/layouts")
CONTROLLERS_DIR = Path("mpcamera/controllers")

# Map .ui filename stem → controller file (Qt Designer naming convention)
UI_TO_CONTROLLER = {
    "cameraPage": "camera_page.py",
    "farmPage": "farm_page.py",
    "samplePage": "samples_page.py",
    "settingsPage": "settings_page.py",
    "resultsWindow": "results_window.py",  # in mpcamera/ui/
    "inferenceTable": None,                # no dedicated controller
    "SoilSight_MainWindow": "ui_nav.py",   # root-level
}

CONTROLLER_SEARCH_DIRS = [CONTROLLERS_DIR, Path("mpcamera/ui"), Path(".")]


def find_controller(ui_stem: str) -> Path | None:
    filename = UI_TO_CONTROLLER.get(ui_stem)
    if not filename:
        return None
    for d in CONTROLLER_SEARCH_DIRS:
        p = d / filename
        if p.exists():
            return p
    return None


def validate_file(ui_path: Path) -> list[str]:
    errors = []
    raw = ui_path.read_text(encoding="utf-8")

    # 1. XML declaration
    if not raw.startswith('<?xml version="1.0" encoding="UTF-8"?>'):
        errors.append("Missing or incorrect XML declaration (must be first line: <?xml version=\"1.0\" encoding=\"UTF-8\"?>)")

    # 2. Parse XML
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        errors.append(f"Invalid XML: {e}")
        return errors

    # 3. Root element
    if root.tag != "ui" or root.get("version") != "4.0":
        errors.append('Root element must be <ui version="4.0">')

    # 4. styleSheet properties must have notr="true"
    for prop in root.iter("property"):
        if prop.get("name") == "styleSheet":
            string_el = prop.find("string")
            if string_el is not None and string_el.get("notr") != "true":
                widget = prop.find("../..") or prop
                errors.append(
                    f'styleSheet property missing notr="true" attribute'
                    f' (near widget name={prop.getparent().get("name") if hasattr(prop, "getparent") else "unknown"})'
                )

    # 5. Indentation check: flag tabs or 4-space indent (Qt Designer uses 1-space)
    for i, line in enumerate(raw.splitlines(), 1):
        stripped = line.lstrip()
        if stripped and line != stripped:
            indent = line[: len(line) - len(stripped)]
            if "\t" in indent:
                errors.append(f"Line {i}: tab indentation detected (Qt Designer uses spaces)")
                break
            if len(indent) % 1 != 0 and len(indent) >= 4 and len(indent) % 4 == 0:
                errors.append(f"Line {i}: 4-space indentation detected (Qt Designer uses 1-space)")
                break

    # 6. Widget name cross-reference with controller
    controller_path = find_controller(ui_path.stem)
    if controller_path:
        controller_text = controller_path.read_text(encoding="utf-8")
        widget_names = [w.get("name") for w in root.iter("widget") if w.get("name")]
        for name in widget_names:
            # Skip generic/internal names
            if name in ("centralwidget", "menubar", "statusbar", "Form", "MainWindow"):
                continue
            if f"self.{name}" not in controller_text and f'findChild' not in controller_text:
                errors.append(f"Widget name '{name}' not referenced as self.{name} in {controller_path}")

    return errors


def main():
    ui_files = sorted(LAYOUTS_DIR.glob("*.ui"))
    if not ui_files:
        print(f"No .ui files found in {LAYOUTS_DIR}")
        sys.exit(1)

    total_errors = 0
    for ui_path in ui_files:
        errors = validate_file(ui_path)
        if errors:
            print(f"✗ {ui_path.name}")
            for e in errors:
                print(f"    {e}")
            total_errors += len(errors)
        else:
            print(f"✓ {ui_path.name}")

    print()
    if total_errors:
        print(f"✗ {total_errors} violation(s) found.")
        sys.exit(1)
    else:
        print("✓ All .ui files valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()
