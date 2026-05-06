# Qlik Atlas — Umgebungskonfiguration

## Übersicht

Das Projekt verwendet getrennte Env-Dateien pro Umgebung. Die aktive Datei
wird beim Start über die Shell-Variable `ENV_FILE` gesteuert.

| Datei | Zweck | Im Git? |
|---|---|---|
| `.env.example` | Vorlage mit allen Variablen | ✅ ja |
| `.env.dev` | Lokale Entwicklung | ✅ ja (keine echten Secrets) |
| `.env.prod` | Produktion | ❌ nein (.gitignore) |
| `.env.staging` | Staging (optional) | ❌ nein (.gitignore) |

---

## Start-Kommandos

```bash
# Entwicklung (Standard)
docker compose up -d

# Produktion (Hetzner / Server)
# Alle Variablen kommen aus .env.prod via env_file — kein --env-file Flag nötig.
docker compose -f docker-compose.prod.yml up -d

# Produktion: Images aktualisieren (nach neuem Release)
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

# Produktion: Logs prüfen
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend

# Mit pgAdmin (nur Dev)
docker compose --profile dev up -d

# Rebuild nach Code-Änderungen (Dev)
docker compose up -d --build backend
docker compose up -d --build frontend
```

---

## Neue Umgebung einrichten

1. `.env.example` kopieren: `cp .env.example .env.prod`
2. Alle `CHANGE_ME`-Werte ersetzen
3. `CREDENTIALS_AES256_GCM_KEY_B64` generieren (siehe Abschnitt unten)
4. `JWT_SECRET` generieren: `openssl rand -base64 64`
5. `PUBLIC_URL` setzen — öffentliche URL des Servers, z.B.:
   - `PUBLIC_URL=http://123.45.67.89:4001` (nur IP/Port)
   - `PUBLIC_URL=https://atlas.your-domain.com` (mit Domain + HTTPS)
6. Datei **nur auf dem Server** ablegen, nie ins Repo

---

## ⚠️ KRITISCH: CREDENTIALS_AES256_GCM_KEY_B64

Dieser AES-256-GCM Key verschlüsselt alle Kunden-Credentials in der Datenbank.

**Regel: Dieser Wert darf sich nach dem ersten Produktiv-Deployment niemals ändern.**

Wenn der Key geändert wird ohne vorherige Re-Encryption der Daten, sind
alle gespeicherten Kunden-Credentials dauerhaft nicht mehr entschlüsselbar.
Es gibt keinen automatischen Recovery-Mechanismus.

### Key generieren

```bash
python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

### Backup-Pflicht

Den generierten Key **zusätzlich** in einem Passwort-Manager als separaten
Eintrag sichern — unabhängig von der `.env.prod` Datei. Wenn die Datei
verloren geht aber der Key noch im Passwort-Manager ist, können die Daten
wiederhergestellt werden.

### Key-Rotation (wenn nötig)

Eine Key-Rotation erfordert einen Re-Encryption-Schritt:
1. Alle verschlüsselten Werte mit dem alten Key auslesen und entschlüsseln
2. Mit dem neuen Key neu verschlüsseln und zurückschreiben
3. `CREDENTIALS_AES256_GCM_KEY_ID` inkrementieren (z.B. `prod-v2`)
4. Erst dann den alten Key in `.env.prod` ersetzen

Ohne diesen Schritt ist eine Rotation nicht möglich.

---

## Variablen-Referenz

| Variable | Beschreibung | Rotation möglich? |
|---|---|---|
| `POSTGRES_PASSWORD` | DB-Passwort | Ja (mit DB-User-Update) |
| `JWT_SECRET` | Signiert Login-Tokens | Ja (loggt alle User aus) |
| `CREDENTIALS_AES256_GCM_KEY_B64` | Verschlüsselt Kunden-Credentials | Nur mit Re-Encryption |
| `CREDENTIALS_AES256_GCM_KEY_ID` | Key-Versions-Label | Mit Key-Rotation |
| `PUBLIC_URL` | Öffentliche Frontend-URL (CORS + CSP) | Jederzeit |
| `FETCH_TRIGGER_TOKEN` | Schützt POST /api/fetch/jobs | Jederzeit |
