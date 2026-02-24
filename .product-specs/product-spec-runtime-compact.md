# Product Spec Runtime (Compact) - qlik_atlas

Nutze diesen Ablauf fuer projektlokale Spec-Arbeit in `qlik_atlas`.

1. Projektkontext bestaetigen (`qlik_atlas`).
2. Anwendbare generelle Specs suchen (Central General Product Specs).
3. Anwendbare Projekt-Specs in `.product-specs/SPECS/` suchen.
4. Tags zuerst fuer Matching nutzen, danach Titel/Inhalt.
5. Konflikte klaeren (general > project, außer explizite User-Ausnahme).
6. Spec-konform arbeiten.
7. Bei Code-/Feature-Aenderungen Testing gemaess `QLIK-PS-002` planen/durchfuehren und Testing Summary liefern.
8. Keine produktiven Daten/Secrets in der Agent-Session verwenden.
