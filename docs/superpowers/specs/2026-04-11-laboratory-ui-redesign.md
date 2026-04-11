# Laboratory UI Redesign — Design Spec

**Date:** 2026-04-11  
**Scope:** Camera page (`cameraPage.ui`) and Results window (`resultsWindow.ui`)  
**Goal:** Make SoilSight feel like a laboratory instrument — data-dense, workflow-clear, and professionally polished — while keeping the existing white/black/blue color scheme.

---

## Shared Design Language

These rules apply to both pages:

- **Page header separator:** `border-bottom: 2px solid #111` below every page title bar
- **Section chrome:** Each instrument section has a `background: #f8f9fa` header strip with a `1px solid #e5e7eb` bottom border, containing a `7px UPPERCASE letter-spacing:1px color:#6b7280` label
- **Digital readouts:** All numeric metric values use `font-variant-numeric: tabular-nums` and bold weight so numbers don't shift width as they update
- **Class badges:** Color-coded pill labels per particle class (fragment = blue `#dbeafe/#1d4ed8`, fiber = purple `#ede9fe/#6d28d9`, film = green `#d1fae5/#065f46`)
- **Font/colors unchanged:** Inter, black buttons (primary), white/light-border buttons (secondary), `#0078d4` / `#2563eb` blue for focus and highlighted values — no new colors introduced

---

## Camera Page Redesign

### Header Bar
Replace the plain `QLabel` title with a two-row header layout:
- Top row (small): `"SoilSight · Camera"` in `9px uppercase #9ca3af`
- Bottom row: `"Microplastic Detection"` in `13px bold #111`
- Right side: live status badge (green dot `#22c55e` + `"CAMERA LIVE"` text on `#f0fdf4` background with `#bbf7d0` border) + breadcrumb chip showing `"Farm / Sample"`
- Separated from content by `border-bottom: 2px solid #111`

The Farm, Sample, Source, and Magnification selectors move into this header bar as compact chips/dropdowns, removing the two rows of combos that currently sit below the title.

### Three-Column Body Layout
Replace the current flat `QVBoxLayout` with a horizontal three-column layout:

**Column 1 — Adjustment sliders (28px wide)**
- Vertical brightness slider with ☀ icon and numeric value label below
- Vertical contrast slider with ◑ icon and numeric value label below
- An `"ADJUST"` rotated label at the top
- This replaces the current side-mounted sliders which flank the camera view

**Column 2 — Camera feed**
- `cameraView` QGraphicsView occupying the full column height
- Below it: 2×2 grid of control buttons with icons prepended:
  - ⏸ Stop Camera / ▶ Start Camera (toggles)
  - ⬆ Upload Image
  - ⊙ Capture Frame
  - ✕ Clear Image

**Column 3 — Instrument panel (120px wide)**
Four bordered instrument sections stacked vertically, each with section chrome header:

1. **MODEL** — `sourceCombo` dropdown for model selection
2. **THRESHOLDS** — 2-cell grid showing Conf and IoU as large bold digital readouts; these remain editable (spinboxes styled as readouts)
3. **RUN INFERENCE** — full-width black primary button
4. **LAST RUN** — read-only metric display: Particles (count), ECD avg (blue), Circ. avg; populated after each inference run; empty/dashed before first run

The `farmCombo`, `soilCombo`, `magnificationSpinbox` move to the header bar. The `viewButton` (☉) and `reloadButton` (⭮) are removed from their own row and integrated as icon actions in the header or instrument panel.

---

## Results Window Redesign

### Header Bar
- Same two-row header pattern as camera page: `"SoilSight · Results"` small label + `"Morphological Characteristics"` bold title
- Right side: breadcrumb chip (Farm / Sample) only — **no Save button in header**
- `border-bottom: 2px solid #111` separator

### Top Panel — Tabbed Image + Stats Sidebar

**Left: Tabbed image view**
- Tab 1 `"Full Image"`: shows the annotated capture with a blue badge overlay showing particle count (e.g. `"247 particles"`)
- Tab 2 `"Particle [ID]"`: shows the cropped/masked particle image for the selected row, zoom/pan enabled, with overlaid badges for class and ECD value
- Clicking a table row automatically switches to Tab 2 and updates the label to the selected particle ID
- Clicking Tab 1 manually returns to the full annotated image

**Right: Stats sidebar (150px wide)**
Two stacked instrument sections:
1. **DISTRIBUTION** — fragment / fiber / film counts with mini horizontal progress bars (colored per class badge scheme)
2. Two-cell grid: **ECD avg** (blue, μm) + **Circ. avg**

### Data Table
Full-width `QTableWidget` below the image panel. Existing columns are kept as-is (no new columns added):
`ID | Class | Confidence | Color | Area (µm²) | Perimeter (µm) | Major Axis | Minor Axis`

Styling:
- Header row: `background: #f8f9fa`, `7px uppercase #6b7280` column labels, `2px solid #e5e7eb` bottom border
- Selected row: `background: #eff6ff`, `outline: 2px solid #2563eb`
- Class column: color-coded badge pill (not plain text)
- Area column: bold blue value (primary metric highlighted)
- No ✓ column added — row deletion is still handled by the "Delete Row" button
- `alternatingRowColors` kept on unselected rows

### Footer Action Bar
Single action bar at the bottom:
- Left: existing status label (e.g. `"Review detected particles before saving."`) unchanged
- Right: **Delete Row** (light/outline button) + **Save to Directus** (black primary button)

---

## Out of Scope

- Farm page, Samples page, Settings page, Home page — low priority, not redesigned
- No new colors introduced beyond what is specified above
- No new data columns added to the results table
- No changes to controller logic, inference pipeline, or data flow
- The `.ui` files are the primary deliverable; QSS changes are embedded in the `.ui` styleSheet properties as they are today

---

## Implementation Notes

- All changes are to `.ui` files in `mpcamera/layouts/` — edit with Qt Designer, not by hand
- The tabbed image panel in the results window requires controller changes in `mpcamera/controllers/camera_page.py` and `mpcamera/ui/results_window.py` to wire up row-selection → tab switch behavior
- The "LAST RUN" instrument section in the camera page needs the controller to populate it after `InferenceWorker` emits `finished`
- The stats sidebar (distribution counts) needs `results_manager.py` to provide per-class counts
- The breadcrumb header chips in the camera page are read-only display labels updated when farm/sample combos change — the combos themselves can be moved or replaced with compact inline selectors
