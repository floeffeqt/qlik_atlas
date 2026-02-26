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


## Fallback-Baseline (wenn private Bridge nicht geladen werden kann)

- Auch ohne private Bridge gelten mindestens folgende Regeln als Baseline:
  - `PS-001` Workflow sichtbar einhalten (Anforderungsanalyse, Aufgabenliste, Plan/Checkliste, systematisches Abarbeiten, Testing, kurze Aenderungsdoku)
  - `PS-005` keine produktiven Daten/Secrets in der Session
  - `PS-004` konsequentes Testing + Testing Summary bei code-/verhaltensrelevanten Aufgaben
- Vor Umsetzung soll ein kurzer Kontext-Report ausgegeben werden (Projektkontext, gelesene Doku, angewendete Regeln, offene Fragen).
