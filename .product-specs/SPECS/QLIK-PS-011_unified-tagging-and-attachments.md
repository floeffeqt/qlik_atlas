---
id: QLIK-PS-011
title: Unified tagging system and customer-scoped attachments with hybrid storage
status: draft
type: feature
priority: p1
product_area: collaboration
tags:
  - tagging
  - attachments
  - file-upload
  - cloud-links
  - collaboration
  - data-lake
  - customer-scoped
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
    - QLIK-PS-003
    - QLIK-PS-001
classification:
  user_impact: high
  business_impact: high
  delivery_risk: medium
  confidence: high
dedup_check:
  compared_specs:
    - PS-001 through PS-006 (general)
    - QLIK-PS-001 through QLIK-PS-010 (project)
  result: partial_overlap
  action: create_new
  notes: >
    Partial overlap with existing tag system (tags + task_tags tables from Migration 0021).
    This spec extends the existing tag system into a unified polymorphic model and adds
    the attachments entity. No conflict — additive extension.
---

## 1. Context

Qlik Atlas verfuegt seit Migration 0021 ueber ein Tag-System (`tags`, `task_tags`), das aktuell nur Tasks abdeckt. Nutzer wuenschen sich, Artefakte aller Art — Dateien, Links, Tasks, Log-Eintraege, Kommentare, READMEs — ueber ein einheitliches Tag-System miteinander zu verbinden. Ziel ist ein kundenuebergreifender "Data Lake" aus strukturierten und unstrukturierten Daten, der ueber Tags navigierbar und filterbar wird.

Zusaetzlich fehlt die Moeglichkeit, Dateien oder Referenzen auf externe Dateien (Cloud-Links) pro Kunde/Projekt zu hinterlegen und zu kategorisieren.

## 2. Problem Statement

- Tags sind aktuell nur an Tasks gebunden (`task_tags`). Andere Entitaeten (Log-Eintraege, Node-Kommentare, READMEs, zukuenftige Attachments) koennen nicht getaggt werden.
- Es gibt keinen Mechanismus, Dateien oder Datei-Referenzen (Links zu Cloud-Speichern) pro Kunde/Projekt zu verwalten.
- Ohne einheitliches Tagging fehlt die Moeglichkeit, entitaetsuebergreifend zu suchen und zu filtern ("Zeig mir alles zu Tag X").

## 3. Goals & Success Metrics

- **G1**: Einheitliches Tag-System, das alle Collaboration-Entitaeten verbindet (Tasks, Attachments, Log-Eintraege, Node-Kommentare, READMEs).
- **G2**: Attachment-Management pro Kunde/Projekt mit Unterstuetzung fuer externe Links (Phase 1) und optionale Datei-Uploads (Phase 2).
- **G3**: Alle Kunden-Mitglieder mit Projektzugriff sehen dieselben Attachments und Tags (RLS-scoped).
- **Metrik**: Nutzer koennen ueber einen Tag-Filter in einer einzelnen Abfrage alle verknuepften Entitaeten abrufen.

## 4. Users / Stakeholders

- **Projektleiter**: Erstellt und verwaltet Attachments und Tags, verknuepft Artefakte projektuebergreifend.
- **Analysten**: Taggen eigene Arbeit (Tasks, Logs), suchen nach getaggten Artefakten.
- **Kunden-Team**: Alle Mitglieder eines Kunden-Projekts teilen sich Tags und Attachments.
- **Entwickler/Agents**: Implementieren das erweiterte Tag-System und Attachment-Storage.

## 5. Scope

### Phase 1: Unified Tags + Link-Attachments

#### 5.1 Polymorphes Tag-System (`entity_tags`)

Neue Tabelle `entity_tags` ersetzt/ergaenzt `task_tags`:

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | SERIAL PK | |
| `tag_id` | FK → tags.id | |
| `entity_type` | VARCHAR(30) | `task`, `attachment`, `log_entry`, `node_comment`, `readme` |
| `entity_id` | INTEGER | ID der referenzierten Entitaet |
| `created_at` | TIMESTAMPTZ | |

- Unique Constraint auf `(tag_id, entity_type, entity_id)` — keine Doppel-Zuordnungen.
- `task_tags` Daten werden in `entity_tags` migriert (mit `entity_type = 'task'`).
- `task_tags` Tabelle wird nach Migration deprecated (ggf. spaeter entfernt).
- RLS: `entity_tags` erbt Zugriff ueber den `tag_id` → `tags.customer_id` Pfad.

#### 5.2 Attachments (Link-Modus)

Neue Tabelle `attachments`:

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | SERIAL PK | |
| `customer_id` | FK → customers.id | Kundenebene (alle Projekte des Kunden sehen es) |
| `project_id` | FK → projects.id | Optional — wenn gesetzt, nur in diesem Projekt sichtbar |
| `uploaded_by` | FK → users.id | Ersteller |
| `title` | VARCHAR(255) | Anzeigename |
| `description` | TEXT | Optionale Beschreibung (Markdown) |
| `storage_type` | VARCHAR(20) | `link` (Phase 1), spaeter `volume`, `s3` |
| `storage_ref` | TEXT | URL (bei `link`), Dateipfad (bei `volume`), S3-Key (bei `s3`) |
| `mime_type` | VARCHAR(100) | Optional — MIME-Typ (bei Links geschaetzt, bei Upload erkannt) |
| `file_size` | BIGINT | Optional — Dateigroesse in Bytes |
| `qlik_app_id` | VARCHAR(255) | Optional — Verknuepfung zu einer Qlik App |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

- RLS Policy: `customer_id` basiert, gleicher Pattern wie andere project-scoped Tabellen.
- Attachments ohne `project_id` sind fuer alle Projekte des Kunden sichtbar.
- Attachments mit `project_id` sind nur in dem Projekt sichtbar.

#### 5.3 API-Endpunkte (Phase 1)

| Bereich | Endpunkte |
|---|---|
| Attachments | `GET /api/attachments` (project_id optional), `POST /api/attachments`, `PUT /api/attachments/{id}`, `DELETE /api/attachments/{id}` |
| Entity-Tags | `POST /api/entity-tags`, `DELETE /api/entity-tags/{id}`, `GET /api/entity-tags?entity_type=&entity_id=` |
| Tag-Suche | `GET /api/tags/{tag_id}/entities` (alle Entitaeten zu einem Tag, gruppiert nach entity_type) |

#### 5.4 Frontend (Phase 1)

- **Dashboard**: Tag-Cloud oder Tag-Filter-Leiste, die entitaetsuebergreifend filtert.
- **Attachments-Bereich**: Eigene Seite oder Dashboard-Card mit Attachment-Liste (Tabelle: Titel, Tags, Typ-Icon, Link, Datum).
- **Tag-Chips**: An allen taggbaren Entitaeten (Tasks, Logs, Attachments, Kommentare) einheitliche Tag-Chips anzeigen.
- **Tag-Vergabe**: Inline-Tag-Selector bei Erstellung/Bearbeitung aller taggbaren Entitaeten.

### Phase 2: Datei-Upload (spaeter)

- `storage_type = 'volume'`: Backend speichert Datei in Named Docker Volume (`atlas_uploads:/app/uploads/{customer_id}/{attachment_id}/`)
- Upload-Endpoint: `POST /api/attachments/upload` (multipart/form-data)
- Download-Endpoint: `GET /api/attachments/{id}/download` (Streaming, RLS-geprueft)
- Max-Dateigroesse konfigurierbar (Default: 50 MB)
- MIME-Type-Whitelist (z.B. PDF, XLSX, DOCX, PNG, JPG, CSV, TXT, ZIP)
- Docker Compose: Named Volume `atlas_uploads` in `docker-compose.yml`
- Fuer Produktion/Multi-Node: Storage-Backend auf MinIO/S3 swappen (gleiche API, nur Konfigurationsaenderung)

## 6. Non-Goals

- Volltextsuche innerhalb hochgeladener Dateien (kein Indexing/OCR).
- Versionierung von Dateien (nur aktueller Stand, kein Git-artiges History).
- Automatische Tag-Erkennung/-Vorschlaege (manuelles Tagging).
- Oeffentliche/anonyme Zugaenglichkeit von Attachments.
- Entfernung der `task_tags`-Tabelle in Phase 1 (nur deprecated, Daten migriert).
- Cloud-Provider-spezifische Integrationen (kein OneDrive/SharePoint API-Anbindung — nur Links).

## 7. Requirements

### Unified Tags
- **R1**: Die Tabelle `entity_tags` MUSS Tags polymorphe an beliebige Entitaeten binden koennen (`entity_type` + `entity_id`).
- **R2**: Unterstuetzte `entity_type`-Werte in Phase 1: `task`, `attachment`, `log_entry`, `node_comment`, `readme`.
- **R3**: Bestehende `task_tags`-Daten MUESSEN in `entity_tags` migriert werden (Alembic Migration).
- **R4**: Der Endpoint `GET /api/tags/{tag_id}/entities` MUSS alle verknuepften Entitaeten gruppiert nach `entity_type` zurueckgeben.
- **R5**: Tag-Zuordnungen MUESSEN ueber `(tag_id, entity_type, entity_id)` unique sein.

### Attachments
- **R6**: Attachments MUESSEN customer-scoped sein (`customer_id` Pflicht, `project_id` optional).
- **R7**: `storage_type = 'link'` MUSS in Phase 1 unterstuetzt werden (externe URL als `storage_ref`).
- **R8**: RLS Policies MUESSEN auf der `attachments`-Tabelle greifen (QLIK-PS-003).
- **R9**: Attachments MUESSEN ueber `entity_tags` taggbar sein (wie alle anderen Entitaeten).
- **R10**: Attachments MUESSEN optional einer Qlik App zugeordnet werden koennen (`qlik_app_id`).

### Docker/Deployment (Phase 2 prep)
- **R11**: Die DB-Schema-Struktur MUSS so designed sein, dass `storage_type` spaeter um `volume` und `s3` erweiterbar ist, ohne Schema-Migration.
- **R12**: Phase 2 Upload MUSS ueber Named Docker Volume (`atlas_uploads`) realisiert werden, organisiert nach `customer_id/attachment_id/`.

## 8. User Flow / Scenarios / Edge Cases

### Szenario 1: Link-Attachment erstellen
1. Nutzer oeffnet Attachments-Bereich (Seite oder Card)
2. Klickt "Neues Attachment"
3. Gibt Titel, URL, optionale Beschreibung ein
4. Waehlt Tags aus vorhandenen Tags oder erstellt neue
5. Optional: Verknuepft mit Qlik App
6. Speichert → Attachment + entity_tags Eintraege werden erstellt

### Szenario 2: Entitaetsuebergreifende Tag-Suche
1. Nutzer klickt auf einen Tag (z.B. "Migration Q2")
2. System zeigt alle Entitaeten mit diesem Tag: 3 Tasks, 2 Attachments, 1 Log-Eintrag
3. Gruppiert nach Typ, jeweils mit Titel/Link

### Szenario 3: Tag an bestehendem Log-Eintrag hinzufuegen
1. Nutzer oeffnet Log-Eintrag im Feed oder Detail
2. Klickt "Tag hinzufuegen"
3. Waehlt aus vorhandenen Tags
4. entity_tags Eintrag wird erstellt

### Edge Case: Attachment ohne Tags
- Erlaubt — Tags sind optional. Attachment ist trotzdem ueber Projekt/Kunde/App filterbar.

### Edge Case: Geloeschter Tag
- Cascade Delete auf `entity_tags` — alle Zuordnungen werden entfernt.
- Attachment/Task/etc. selbst bleibt erhalten.

### Edge Case: Externer Link nicht erreichbar
- Kein Health-Check durch das System. Nutzer ist verantwortlich fuer Link-Pflege.
- Optional spaeter: Link-Validierung als Hintergrund-Job (nicht in Phase 1).

## 9. Acceptance Criteria

- **AC-001**: Ein Tag kann ueber `entity_tags` an Tasks, Attachments, Log-Eintraege, Node-Kommentare und READMEs gebunden werden.
- **AC-002**: `GET /api/tags/{tag_id}/entities` liefert alle verknuepften Entitaeten gruppiert nach `entity_type`.
- **AC-003**: Bestehende `task_tags`-Eintraege sind nach Migration in `entity_tags` mit `entity_type = 'task'` vorhanden.
- **AC-004**: Ein Attachment mit `storage_type = 'link'` kann erstellt, gelesen, aktualisiert und geloescht werden.
- **AC-005**: Attachments sind ueber RLS nur fuer berechtigte Kunden-Mitglieder sichtbar (QLIK-PS-003).
- **AC-006**: Ein Attachment kann mit mehreren Tags und optional mit einer Qlik App verknuepft werden.
- **AC-007**: Im Frontend koennen Tags an allen unterstuetzten Entitaeten hinzugefuegt und entfernt werden.
- **AC-008**: Ein Tag-Klick im Frontend zeigt alle verknuepften Entitaeten entitaetsuebergreifend an.

## 10. Dependencies / Risks / Assumptions

### Abhaengigkeiten
- Migration 0021/0022 (Collaboration-Modul) muss applied sein (Tags + task_tags existieren).
- QLIK-PS-003 (RLS): Neue Tabellen benoetigen RLS Policies.
- QLIK-PS-008: Alembic-Migrationsname max 30 Zeichen.

### Risiken

| Risiko | Auswirkung | Wahrscheinlichkeit | Mitigation | Restrisiko |
|---|---|---|---|---|
| Polymorphes Tagging ohne FK-Constraint auf `entity_id` | Verwaiste Tags bei geloeschten Entitaeten | medium | Application-level Cascade bei Entity-Delete; periodischer Cleanup-Job | Minimal — verwaiste Tags sind funktional harmlos |
| Externe Links werden ungueltig | Nutzer klickt auf toten Link | medium | UI-Hinweis "externer Link"; optional spaeter Link-Check-Job | Akzeptabel — Nutzer-Verantwortung |
| Migration von `task_tags` → `entity_tags` bei laufendem System | Kurzer Moment ohne Tag-Zuordnungen | low | Alembic Migration mit INSERT...SELECT in einer Transaktion | Keins bei korrekter Migration |

### Annahmen
- Kunden nutzen bereits Cloud-Speicher (SharePoint, Google Drive, Confluence, etc.) fuer Dateien.
- Phase 1 (Links) deckt den Grossteil der Use Cases ab; direkter Upload ist Nice-to-have.
- Das bestehende `tags`-Tabellen-Schema (id, customer_id, name, color) bleibt unveraendert.

## 11. Rollout / Release Considerations

- **Phase 1** (Unified Tags + Link-Attachments): Eigene Alembic Migration, Backend-Endpunkte, Frontend-Integration. Kein Breaking Change fuer bestehende Task-Tag-Nutzung (Backward-Compatible API).
- **Phase 2** (File Upload): Separater Release mit Docker Volume Config und Upload-Endpoints. Kann unabhaengig von Phase 1 zeitlich geplant werden.
- Bestehende `POST /api/task-tags` und `DELETE /api/task-tags/{task_id}/{tag_id}` bleiben als Convenience-Wrapper erhalten, leiten intern auf `entity_tags` um.

## 12. Open Questions

- Soll `task_tags` nach vollstaendiger Migration sofort entfernt oder als deprecated View beibehalten werden?
- Soll es eine maximale Anzahl Tags pro Entitaet geben?
- Soll Phase 2 (Upload) MinIO als self-hosted S3-Alternative in Docker Compose einbinden, oder reicht ein Named Volume fuer den Start?
