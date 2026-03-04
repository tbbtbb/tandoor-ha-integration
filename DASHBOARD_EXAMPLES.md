# 🎨 Dashboard Beispiele

## Meal-Plan Karte mit Bild

```yaml
type: picture-entity
entity: sensor.tandoor_int_heute
name: "Heute"
show_state: true
show_name: true
```

## Wochenübersicht (vertikal)

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: "## 🍽️ Essensplan"
  - type: entities
    entities:
      - entity: sensor.tandoor_int_heute
        name: "Heute"
        icon: mdi:food
      - entity: sensor.tandoor_int_morgen
        name: "Morgen"
        icon: mdi:food-outline
      - entity: sensor.tandoor_int_uebermorgen
        name: "Übermorgen"
        icon: mdi:food-off
      - entity: sensor.tandoor_int_naechste_gerichte
        name: "Gerichte geplant"
        icon: mdi:calendar-check
```

## Shopping + Bring! Sync

```yaml
type: vertical-stack
cards:
  - type: entities
    title: "🛒 Einkaufsliste"
    entities:
      - entity: sensor.tandoor_int_zutaten
        name: "Offene Zutaten"
  - type: horizontal-stack
    cards:
      - type: button
        name: "Laden"
        icon: mdi:refresh
        tap_action:
          action: call-service
          service: tandoor.load_from_tandoor
      - type: button
        name: "→ Bring!"
        icon: mdi:cart-arrow-up
        tap_action:
          action: call-service
          service: tandoor.sync_to_bring
```

## Update-Status

```yaml
type: conditional
conditions:
  - entity: sensor.tandoor_int_update_status
    state: update_available
card:
  type: markdown
  content: >
    ## ⬆️ Tandoor Update verfügbar!
    {{ state_attr('sensor.tandoor_int_update_status', 'status_text') }}
    [Release Notes]({{ state_attr('sensor.tandoor_int_update_status', 'release_url') }})
```

## Automations-Beispiel: Update-Benachrichtigung

```yaml
automation:
  alias: "Tandoor Update Notification"
  trigger:
    - platform: state
      entity_id: sensor.tandoor_int_update_status
      to: "update_available"
      for:
        minutes: 5
  action:
    - service: persistent_notification.create
      data:
        title: "📦 Tandoor Update verfügbar!"
        message: >
          {{ state_attr('sensor.tandoor_int_update_status', 'status_text') }}
          Veröffentlicht: {{ state_attr('sensor.tandoor_int_update_status', 'release_date') }}
        notification_id: tandoor_update_notification
```

## Bild-Karte für heutiges Gericht

```yaml
type: picture-glance
title: "Heute auf dem Speiseplan"
entities:
  - sensor.tandoor_int_heute
camera_image: sensor.tandoor_int_heute
```
