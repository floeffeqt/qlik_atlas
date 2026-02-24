# AGENTS (Project Bridge: qlik_atlas)

## Zentrale Agent-Governance (Desktop\Ki)

- Fuer **alle** neuen Agent-Sessions und Aufgaben in diesem Projekt den zentralen Gateway-Masterprompt verwenden:
  - `C:\Users\MauriceOkoye\Desktop\Ki\Masterprompts\spec-aware-chat-gateway.md`
- Zusaetzliche passende Masterprompts aus `C:\Users\MauriceOkoye\Desktop\Ki\Masterprompts\` muessen per Gateway-Matching beruecksichtigt werden.
- Bei code-/verhaltensrelevanten Aufgaben ist insbesondere relevant:
  - `C:\Users\MauriceOkoye\Desktop\Ki\Masterprompts\testing-execution-runtime.md`
- Fuer Spec-Erstellung/-Review verwenden (zus?tzlich zum Gateway, wenn passend):
  - `C:\Users\MauriceOkoye\Desktop\Ki\Masterprompts\product-spec-runtime-compact.md`

## Spec-Quellen (qlik_atlas)

- Generelle Specs (zentral): `C:\Users\MauriceOkoye\Desktop\Ki\specs\GENERAL_PRODUCT_SPECS\SPECS\`
- Projektspezifische Specs (dieses Repo): `.product-specs\SPECS\`
- Projektindex: `.product-specs\spec-index.md`

## Prioritaet und No-Match

- Standard: `general` Specs haben Vorrang vor `project` Specs, ausser der User verlangt explizit etwas anderes.
- Wenn kein passender Spec auf den Prompt zutrifft: User informieren und Bestaetigung einholen (ohne Spec fortfahren vs. neuen Spec erstellen).

## Data Safety (hart)

- Keine produktiven Daten oder produktiven Secrets in Agent-Sessions verwenden, testen, loggen oder ausgeben.
- Nur sichere Alternativen verwenden: `synthetic`, `sanitized`, `mock`, `staging-non-prod`.

## Testing (verbindlich bei relevanten Aufgaben)

- Testing nach anwendbaren general + project Testing-Specs planen/durchfuehren.
- Endergebnis mit strukturiertem Testing Summary gem?ss `C:\Users\MauriceOkoye\Desktop\Ki\specs\TEMPLATES\TESTING_SUMMARY.md` berichten.

