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
