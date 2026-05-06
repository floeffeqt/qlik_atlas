---
id: QLIK-PS-010
title: Standardized collapsible card UI pattern for expandable dashboard sections
status: draft
type: improvement
priority: p2
product_area: frontend
tags:
  - frontend
  - ui-pattern
  - collapsible
  - dashboard
  - expandable
  - card
  - consistency
spec_scope: project
project_key: qlik_atlas
owners: []
reviewers: []
created: 2026-03-27
updated: 2026-03-27
target_release: null
links:
  epics: []
  tickets: []
  adrs: []
  related_specs:
    - QLIK-PS-006
classification:
  user_impact: medium
  business_impact: low
  delivery_risk: low
  confidence: high
dedup_check:
  compared_specs:
    - PS-001 through PS-006 (general)
    - QLIK-PS-001 through QLIK-PS-009 (project)
  result: unique
  action: create_new
  notes: No existing spec covers frontend UI patterns or component styling conventions.
---

## 1. Context

Qlik Atlas verwendet in mehreren Frontend-Seiten (Dashboard, App-Detail, Projekte) Karten-Elemente (`card`), die einklappbar sind. Bisher gab es keine verbindliche Vorgabe, wie solche expandierbaren Elemente strukturiert und gestylt werden. Die App-Uebersicht im Dashboard wurde als erstes Element mit dem neuen Pattern implementiert (2026-03-27) und dient als Referenz.

## 2. Problem Statement

Ohne einheitliches Pattern fuer expandierbare Karten entstehen inkonsistente UX-Muster: unterschiedliche Toggle-Indikatoren, unterschiedliche Klick-Bereiche, unterschiedliche Zustandsanzeigen. Das erschwert sowohl die Nutzung als auch die Wartung.

## 3. Goals & Success Metrics

- **Konsistenz**: Alle expandierbaren Karten im Projekt verwenden dasselbe visuelle und interaktive Pattern.
- **Wiedererkennbarkeit**: Nutzer erkennen sofort, dass ein Element expandierbar ist, anhand des Indikators.
- **Messbar**: Bei Code-Review sind keine abweichenden Collapsible-Implementierungen mehr vorhanden.

## 4. Users / Stakeholders

- **Endnutzer**: Projektleiter und Analysten, die das Dashboard und Detail-Seiten nutzen.
- **Entwickler/Agents**: Muessen bei neuen expandierbaren Elementen das Pattern anwenden.

## 5. Scope

Dieses Pattern gilt fuer alle expandierbaren/einklappbaren Karten-Elemente (`card`) im Qlik Atlas Frontend, die per Klick auf den Header ein-/ausgeklappt werden.

### Verbindliches Pattern

#### HTML-Struktur
- Aeusserer Container: `<div class="card">` (bestehende Card-Klasse)
- Header: `<div class="card-header">` mit `cursor:pointer; user-select:none` und `onclick`-Handler
- Titel: `<span class="card-title">` mit dem Abschnittsnamen
- Optional: Zaehler/Badge `<span>` neben dem Titel (z.B. Anzahl Elemente)
- Toggle-Indikator: `<span>` mit `margin-left:auto; font-size:0.72rem; color:var(--text-dim)` rechtsbuendig im Header
- Body: `<div>` mit dem eigentlichen Inhalt, initial `style="display:none"` wenn standardmaessig eingeklappt

#### Toggle-Indikator (visuell)
- Eingeklappt: `▶ Einblenden`
- Ausgeklappt: `▼ Ausblenden`
- Schriftgroesse: `0.72rem`
- Farbe: `var(--text-dim)`

#### JavaScript-Verhalten
- Boolean-State-Variable (`_xyzExpanded = false`)
- Toggle-Funktion aendert `display` des Body-Elements (`''` oder `'none'`) und aktualisiert den Indikator-Text
- Toggle-Funktion muss auf `window` exponiert werden (IIFE-Kompatibilitaet)
- Klickbereich ist der gesamte Card-Header

#### Referenz-Implementierung
- `frontend/index.html`: App-Uebersicht (`#appHealthCard`, `toggleHealthCard()`)

## 6. Non-Goals

- Animationen oder Transitions beim Ein-/Ausklappen (bewusst nicht vorgesehen, um Einfachheit zu wahren).
- Verschachtelte Collapsible-Elemente (Akkordeon-in-Akkordeon).
- Aenderung bestehender Elemente, die kein Collapsible-Verhalten haben.
- Generische UI-Komponentenbibliothek oder Framework-Einfuehrung.

## 7. Requirements

- **R1**: Jedes neue expandierbare Karten-Element MUSS die HTML-Struktur aus Abschnitt 5 verwenden (card > card-header mit pointer + onclick > card-title + toggle-indikator + body).
- **R2**: Der Toggle-Indikator MUSS die Zeichen `▶`/`▼` mit den Labels `Einblenden`/`Ausblenden` verwenden.
- **R3**: Die Toggle-Funktion MUSS auf `window` exponiert werden, damit `onclick`-Handler aus dem HTML funktionieren (IIFE-Kontext).
- **R4**: Der initiale Zustand (eingeklappt oder ausgeklappt) ist pro Element frei waehlbar, muss aber konsistent mit dem angezeigten Indikator sein.
- **R5**: Bestehende expandierbare Elemente (z.B. "Apps ohne README") SOLLEN bei naechster Bearbeitung auf dieses Pattern migriert werden.

## 8. User Flow / Scenarios / Edge Cases

### Szenario 1: Nutzer sieht eingeklappte Karte
- Header zeigt Titel, optionalen Zaehler und `▶ Einblenden`
- Body ist nicht sichtbar

### Szenario 2: Nutzer klickt auf Header
- Body wird sichtbar
- Indikator wechselt zu `▼ Ausblenden`

### Szenario 3: Nutzer klickt erneut auf Header
- Body wird wieder ausgeblendet
- Indikator wechselt zurueck zu `▶ Einblenden`

### Edge Case: Daten noch nicht geladen
- Body zeigt "Lade..." Platzhalter, Toggle funktioniert trotzdem
- Daten werden unabhaengig vom Collapse-Zustand geladen (nicht lazy)

## 9. Acceptance Criteria

- **AC-001**: Neue expandierbare Karten verwenden `▶ Einblenden` / `▼ Ausblenden` als Toggle-Indikator im Card-Header.
- **AC-002**: Der gesamte Card-Header ist klickbar (nicht nur der Indikator-Text).
- **AC-003**: Indikator-Text und Body-Sichtbarkeit sind nach jedem Toggle-Klick konsistent.
- **AC-004**: Toggle-Funktionen sind ueber `window.functionName` aufrufbar.
- **AC-005**: Styling des Indikators entspricht `font-size: 0.72rem; color: var(--text-dim); margin-left: auto`.

## 10. Dependencies / Risks / Assumptions

### Annahmen
- Das bestehende CSS-Variablen-System (`--text-dim`, `--border`, etc.) bleibt stabil.
- Alle Frontend-Seiten verwenden weiterhin die bestehende `card`/`card-header`/`card-title` Klassenstruktur.

### Risiken
- **Gering**: Bestehende Elemente mit eigenem Collapsible-Pattern (z.B. "Apps ohne README" mit `btn-sm`-Toggle) weichen noch ab. Migration erfolgt bei naechster Bearbeitung (R5), kein sofortiger Bruch.

### Abhaengigkeiten
- Keine externen Abhaengigkeiten. Reines CSS + Vanilla JS Pattern.

## 11. Rollout / Release Considerations

- Pattern gilt ab sofort fuer neue expandierbare Elemente.
- Bestehende Elemente werden opportunistisch migriert (bei naechster Bearbeitung der jeweiligen Seite).
- Kein Breaking Change, da nur additive Styling-Konvention.

## 12. Open Questions

- none
