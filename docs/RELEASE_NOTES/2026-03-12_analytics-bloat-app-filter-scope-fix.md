---
doc_type: release-note
scope: project
project_key: qlik_atlas
status: active
tags:
  - analytics
  - frontend
  - bloat
  - filters
updated: 2026-03-12
owners: []
source_of_truth: no
related_specs:
  - QLIK-PS-002
  - QLIK-PS-004
  - QLIK-PS-006
  - QLIK-PS-009
related_docs:
  - docs/RELEASE_NOTES/README.md
---

# Release Note: Analytics Bloat App Filter Scope Fix

## Datum

- 2026-03-12

## Summary

- Die App-Filter im Modul `Data Model & Capacity` nutzen im Bloat-Bereich nicht mehr nur die lokal gekuerzten Tabellenzeilen.
- Die Filteroptionen fuer `Top Apps by Size`, `Top Tables by Byte Size`, `Top Fields by Byte Size` und `Schema Drift Apps` werden jetzt aus dem vollstaendigen Projekt-App-Scope aufgebaut.
- Der Bloat-Fetch in `frontend/analytics.html` wurde von `limit=25` auf `limit=200` angehoben, damit der sichtbare Scope fuer die Filter deutlich weniger aggressiv beschnitten wird.
- Die drei Top-Tabellen (`Top Apps`, `Top Tables`, `Top Fields`) reagieren jetzt auf bereits gesetzte Filter und bieten einen `Filter aufheben`-Button je Tabelle.

## Frontend

- `frontend/analytics.html`:
  - Filterwerte und Filterlabels werden getrennt behandelt, damit App-Namen sichtbar bleiben und intern weiter ueber `app_id` gefiltert wird.
  - `renderFilterableTable(...)` erzeugt Filteroptionen jetzt kontextabhaengig aus den uebrigen aktiven Tabellenfiltern.
  - Die Bloat-Tabellen werden nicht mehr mit `.slice(0,20)` vor dem Rendern gekappt.
  - Die App-Filter nutzen `app_id` als Vergleichswert und den sichtbaren App-Namen als Label.
  - Die drei Top-Tabellen haben einen Reset-Knopf fuer die komplette Tabellenfilterung.

## Hinweis

- Der Fix aendert keine Backend-Response-Schemata und keine DB-Struktur.
- Falls ein Projekt mehr als 200 relevante Bloat-Zeilen im Scope hat und weiterhin Randfaelle auftreten, ist der naechste saubere Schritt ein serverseitig app-spezifischer Bloat-Fetch statt weiterer pauschaler Limits.
