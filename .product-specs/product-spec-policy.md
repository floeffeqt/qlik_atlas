# Product Spec Policy (Project: qlik_atlas)

Project-local Ergänzungen zur zentralen Product-Spec-Governance.

Zentrale Referenzen (verbindlich):
- `Desktop/Ki/Masterprompts/spec-aware-chat-gateway.md`
- `Desktop/Ki/Masterprompts/product-spec-runtime-compact.md`
- `Desktop/Ki/specs/POLICY/product-spec-policy.md`

Projektregeln (ergänzend):
- Generelle Specs gelten zuerst, projektspezifische Specs ergänzen (außer explizite User-Ausnahme im Einzelfall).
- Projekt-Specs in `.product-specs/SPECS/` müssen `tags` im YAML Header pflegen.
- Testing für Code-/Feature-Änderungen muss das Projekt-Testing-Konzept (`QLIK-PS-002`) berücksichtigen.
- Produktive Daten und produktive Secrets dürfen nicht in Agent-Sessions verwendet werden (siehe zentrale generelle Specs, insbesondere `PS-005`).
- Bei Änderungen am DB-Schema/-Modell (Tabellen, Spalten, PK/FK, materialisierte Payload-Spalten, fachliche Join-Keys, RLS-relevante Modellstruktur) MUSS `docs/DB_MODEL.md` in derselben Aufgabe mit geprüft und bei Bedarf aktualisiert werden.
- Bei DB-bezogenen Aufgaben soll `docs/DB_MODEL.md` in den Kontextscan aufgenommen werden; falls keine Änderung nötig ist, ist das kurz zu benennen.
