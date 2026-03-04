# 🍽️ Tandoor Recipes – Home Assistant Integration

Private HACS-Integration für [Tandoor Recipes](https://github.com/TandoorRecipes/recipes).

## Features

- **Meal-Plan Sensoren** – Heutiges, morgiges und übermorgiges Gericht mit Bild
- **Nächste Gerichte** – Übersicht aller geplanten Mahlzeiten
- **Shopping-Liste** – Ungecheckte Zutaten als Sensor
- **Bring! Sync** – Zutaten per Service zu Bring! übertragen & in Tandoor abhaken
- **Update-Check** – Neue Tandoor-Versionen via GitHub erkennen
- **Backup-Monitoring** – Letztes Proxmox-Backup überwachen (optional, via SSH)

## Installation via HACS

1. HACS → **Custom Repositories** → `https://github.com/USER/tandoor-integration` → Typ: **Integration**
2. HACS → Integrationen → **Tandoor Recipes** → Installieren
3. Home Assistant neu starten
4. **Einstellungen → Integrationen → + Hinzufügen → Tandoor Recipes**

## Konfiguration (Config Flow)

### Schritt 1: Tandoor Verbindung
| Feld | Beschreibung | Standard |
|------|-------------|---------|
| Tandoor URL | URL deiner Tandoor-Instanz | `http://192.168.178.124:8090` |
| API Token | Bearer Token aus `/api/user-token-create/` | – |
| Space ID | Deine Space-ID (meist 1) | `1` |
| Update-Intervall | Sekunden zwischen API-Abfragen | `300` |

> **Tipp:** Den API-Token bekommst du unter `http://DEINE-URL/api/user-token-create/`

### Schritt 2: Bring! (Optional)
Aktiviere die Bring!-Integration und wähle deine Todo-Entität (z.B. `todo.zuhause`).

### Schritt 3: Backup-Monitoring (Optional)
SSH-Zugang zu deinem Proxmox-Host für Backup-Überwachung.

### Schritt 4: Versions-Check (Optional)
GitHub API wird für Update-Erkennung genutzt – kein Account nötig.

## Sensoren

| Entität | Beschreibung |
|---------|-------------|
| `sensor.tandoor_int_heute` | Heutiges geplantes Gericht |
| `sensor.tandoor_int_morgen` | Morgiges geplantes Gericht |
| `sensor.tandoor_int_uebermorgen` | Übermorgen |
| `sensor.tandoor_int_naechste_gerichte` | Anzahl geplanter Gerichte (heute+) |
| `sensor.tandoor_int_zutaten` | Anzahl ungecheckter Einkaufslisten-Items |
| `sensor.tandoor_int_latest_version` | Neueste Tandoor-Version (GitHub) |
| `sensor.tandoor_int_update_status` | `up_to_date` oder `update_available` |
| `sensor.tandoor_int_installed_version` | Installierte Version (benötigt SSH) |
| `sensor.tandoor_int_backup_status` | Letztes Proxmox-Backup (benötigt SSH) |

## Services

### `tandoor.load_from_tandoor`
Lädt Daten aus Tandoor und zeigt eine Zusammenfassung per Notification.

```yaml
service: tandoor.load_from_tandoor
```

### `tandoor.sync_to_bring`
Sendet alle ungecheckten Zutaten an Bring! und hakt sie in Tandoor ab.

```yaml
service: tandoor.sync_to_bring
```

### `tandoor.reset_status`
Setzt den internen Sync-Status zurück.

```yaml
service: tandoor.reset_status
```

## Dashboard-Beispiel

```yaml
type: vertical-stack
cards:
  - type: entity
    entity: sensor.tandoor_int_heute
    name: "🍽️ Heute"
  - type: entity
    entity: sensor.tandoor_int_morgen
    name: "📅 Morgen"
  - type: entity
    entity: sensor.tandoor_int_zutaten
    name: "🛒 Einkaufen"
  - type: button
    name: "Zu Bring! senden"
    icon: mdi:cart-arrow-up
    tap_action:
      action: call-service
      service: tandoor.sync_to_bring
```

## Bekannte Probleme & Lösungen

### Meal-Plan 403 Forbidden
**Problem:** API gibt 403 zurück  
**Lösung:** Prüfe Space ID (Standard: 1). Die Integration fügt `&space={id}` automatisch hinzu.

### Docker Pull schlägt fehl (DNS)
**Problem:** Tailscale DNS kann Docker Hub nicht auflösen  
**Lösung:** Temporär: `echo "nameserver 8.8.8.8" >> /etc/resolv.conf` im LXC-Container

### SSH-Verbindung schlägt fehl
**Problem:** asyncssh Fehler  
**Lösung:** Backup-Monitoring und Docker-Versions-Check in den Einstellungen deaktivieren

## Lizenz

Privat – nicht für öffentliche Distribution gedacht.
