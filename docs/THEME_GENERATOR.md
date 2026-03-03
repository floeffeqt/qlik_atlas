---
doc_type: feature-guide
scope: project
project_key: qlik_atlas
status: active
tags:
  - theme-generator
  - frontend
  - backend
  - zip-export
updated: 2026-03-03
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-002
  - QLIK-PS-005
  - QLIK-PS-006
related_docs:
  - docs/INDEX.md
---

# Theme Generator (MVP)

## Scope

- Provides a new authenticated Theme Builder UI at `/theme-builder.html`.
- Generates a downloadable production ZIP from `POST /api/themes/build`.
- Upload is intentionally not implemented yet (`POST /api/themes/upload` returns `501`).
- Frontend includes a guided property editor with:
  - auto-selected input types (color picker, select, number, text, palette/array controls)
  - readable select/dropdown options (dark background + light text)
  - short per-property descriptions
  - JSON sync (guided changes update `theme.json` and vice versa)
  - property-catalog by levels (`level1`/`level2`/`level3`) with multi-select insert
  - catalog inserts full property blocks by default (all known sub-attributes), not only single leaf attributes
  - object-specific defaults are prefilled according to Qlik theme docs (for example chart/object blocks such as `scatterPlot`, `lineChart`, `listBox`, `mapChart`, `waterfallChart`, `straightTable`/`straightTableV2`)
  - for inserted `object.*` blocks, the full attribute structure is generated but leaf values are intentionally empty, so users can fill them explicitly in the guided editor
  - explicit templates for `palettes.data` types (`row`, `pyramid`) and `scales` types (`gradient`, `class`)
  - required-field hints:
    - catalog entries list required attributes
    - guided property rows mark required attributes and show missing-required state
  - guided editor tree view:
    - collapsible path groups (for example `object > grid > line`)
    - grouped visibility of related sub-attributes while editing
  - inserted-object focus:
    - when object blocks are inserted from the catalog, guided object view is reduced to these inserted `object.*` blocks instead of showing unrelated object trees
    - visual object chips represent only the active inserted visualization objects
  - live visualization preview:
    - sticky canvas preview is placed directly in Guided Editor, so it remains visible while editing
    - preview follows the currently edited/selected visualization object
    - preview colors are resolved from current JSON values and `_variables` references
    - additional preview property board lists all editierbaren Felder des aktiven Objekts (inkl. OFF-Status), so every editable element is visible in the preview area
  - per-attribute presence toggle (`ON/OFF`) in guided editor:
    - `OFF` removes the attribute key from JSON
    - `ON` re-adds the attribute key with schema default/empty seed
    - toggled-off attributes stay visible in guided editor so they can be re-enabled later
  - retro UI styling for attribute toggles is modular (`ui-retro`/`ui-clean` mode), so it can be globally disabled later without changing core editor logic
  - remove actions for single properties and selected catalog templates
  - editor clear actions (`{}` reset and complete editor clear)
  - variable manager for `_variables`:
    - create new variables
    - edit variable names and values
    - rename propagation updates theme references that use the old variable token
  - color lab:
    - circular color wheel with full spectrum + brightness control
    - color search by HEX (`#870414`) or RGB (`rgb(135,4,20)`)
    - copy HEX/RGB and apply directly to variable input fields

## Backend API

### Build ZIP

- Endpoint: `POST /api/themes/build`
- Auth: Bearer token required
- Input:
  - `theme_name` / `file_basename`
  - `qext` metadata object
  - full `theme_json` object (free JSON, not restricted to a small token subset)
- Output: `application/zip` download

ZIP content:
- `theme.json`
- `<file_basename>.qext`

### Upload Stub

- Endpoint: `POST /api/themes/upload`
- Auth: Bearer token required
- Current behavior: HTTP `501 not implemented` with explanatory payload

## Frontend Usage

1. Open `/theme-builder.html` after login.
2. Configure filename and QEXT metadata fields.
3. Use the property catalog (level filters + multi-select) to add one or more specific properties/templates to the theme JSON.
4. Use the guided property editor to change existing theme properties with matching controls and short descriptions.
5. Optionally edit the full `theme.json` directly (all Qlik theme properties possible).
6. Click `ZIP bauen & downloaden` to build and download the production bundle.
7. `Upload (Stub)` currently confirms that server-side upload is not implemented.

## Runtime/Data Handling

- ZIP generation is fully in-memory at request time.
- No productive theme payload artifacts are persisted on local runtime filesystem.
- No database schema changes were required for this MVP.
