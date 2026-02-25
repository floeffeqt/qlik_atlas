# AGENTS (Project Bridge: qlik_atlas)

Dieses Projekt nutzt eine **zentrale AGENTS-Bridge** ausserhalb des Repos, um private Pfade nicht zu veroeffentlichen. Bitte eine eigene Logik einbauen, um auf das eigene private Masterprompt repo zuzugreifen.

## Zentrale Bridge (privat, nicht committen)

- Ort (lokal auf deinem System): `<KI_ROOT>\projects\qlik_atlas\AGENTS.md`

## Hinweis

- Diese Datei enthaelt **keine privaten Pfade** und darf ins Repo.
- Die eigentliche Bridge mit absoluten Pfaden liegt **nur lokal** im KI-Ordner.


## Dokumentation (Projektkontext)

- Projekt-Doku-Einstieg im Repo: `docs/INDEX.md`
- Bestehende Root-Dokumente (`REQUIREMENTS.md`, `PROJECT_STATUS.md`, `FIXES_APPLIED.md`) werden ueber `docs/INDEX.md` referenziert und weiter genutzt.
- Doku-Regeln und Scan-Reihenfolge liegen zentral in `<KI_ROOT>\documentation\POLICY\...` und werden ueber die private Bridge angewendet.
