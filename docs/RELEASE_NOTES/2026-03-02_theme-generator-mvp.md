---
doc_type: release-notes
scope: project
project_key: qlik_atlas
status: active
tags:
  - release-notes
  - theme-generator
  - zip-export
updated: 2026-03-02
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-002
  - QLIK-PS-005
  - QLIK-PS-006
related_docs:
  - docs/THEME_GENERATOR.md
  - docs/INDEX.md
---

# Theme Generator MVP (Production ZIP + Upload Stub)

## Summary

- Added a new backend theme module with authenticated endpoints:
  - `POST /api/themes/build` (in-memory production ZIP generation)
  - `POST /api/themes/upload` (explicit `501` stub)
- Added a new frontend page `/theme-builder.html` with:
  - QEXT metadata form
  - property-catalog by levels with multi-select insertion
  - guided property editor (auto input types + short per-property descriptions)
  - full JSON editor for `theme.json` (all Qlik theme properties editable)
  - ZIP download action (2 files only)
  - upload-stub action
- Added automated backend tests for ZIP content, QEXT payload, and `theme.json` validation.

## Notes

- No DB schema/model change was needed.
- ZIP generation does not persist productive payloads on local filesystem in runtime.
- Output ZIP now intentionally contains only `theme.json` and `<name>.qext` (no README/schema/css extras).
- Added explicit catalog templates for `palettes.data` (`row`, `pyramid`) and `scales` (`gradient`, `class`).
- Added remove controls:
  - delete single property in guided editor
  - remove selected catalog templates
  - clear JSON (`{}`) and complete editor clear actions
