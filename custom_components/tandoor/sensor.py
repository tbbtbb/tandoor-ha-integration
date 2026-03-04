"""Sensor platform for Tandoor Recipes integration."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    SENSOR_HEUTE,
    SENSOR_MORGEN,
    SENSOR_UEBERMORGEN,
    SENSOR_NAECHSTE,
    SENSOR_ZUTATEN,
    SENSOR_INSTALLED_VERSION,
    SENSOR_LATEST_VERSION,
    SENSOR_UPDATE_STATUS,
    SENSOR_BACKUP_STATUS,
    CONF_ENABLE_VERSION_CHECK,
    CONF_ENABLE_DOCKER_VERSION,
    CONF_ENABLE_BACKUP,
)
from .coordinator import TandoorDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class TandoorEntity(CoordinatorEntity):
    """Gemeinsame Basisklasse für alle Tandoor-Entitäten.

    Setzt device_info automatisch → alle Sensoren erscheinen unter
    einem Gerät in Einstellungen → Geräte & Dienste → Tandoor Recipes.
    """

    def __init__(self, coordinator: TandoorDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)  # CoordinatorEntity braucht nur coordinator
        self._entry_id = entry_id

    @property
    def device_info(self):
        """Alle Sensoren gehören zum selben virtuellen Gerät."""
        return self.coordinator.device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tandoor sensors from a config entry."""
    coordinator: TandoorDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    config = coordinator.config
    eid = entry.entry_id  # Basis für alle unique_ids → UI-Umbenennung funktioniert

    entities: list[SensorEntity] = [
        TandoorDaySensor(coordinator, eid, "heute", 0, SENSOR_HEUTE, "Tandoor Heute"),
        TandoorDaySensor(coordinator, eid, "morgen", 1, SENSOR_MORGEN, "Tandoor Morgen"),
        TandoorDaySensor(coordinator, eid, "uebermorgen", 2, SENSOR_UEBERMORGEN, "Tandoor Übermorgen"),
        TandoorNextMealsSensor(coordinator, eid),
        TandoorShoppingSensor(coordinator, eid),
    ]

    if config.get(CONF_ENABLE_VERSION_CHECK, True):
        entities.append(TandoorLatestVersionSensor(coordinator, eid))
        entities.append(TandoorUpdateStatusSensor(coordinator, eid))

    if config.get(CONF_ENABLE_DOCKER_VERSION, False):
        entities.append(TandoorInstalledVersionSensor(coordinator, eid))

    if config.get(CONF_ENABLE_BACKUP, False):
        entities.append(TandoorBackupStatusSensor(coordinator, eid))

    async_add_entities(entities)


def _get_meals_for_day(coordinator: TandoorDataUpdateCoordinator, day_offset: int) -> list[dict]:
    """Return meals for a specific day offset from today."""
    from datetime import date, timedelta
    target_date = (date.today() + timedelta(days=day_offset)).isoformat()
    results = coordinator.data.get("meal_plan", {}).get("results", [])
    return [
        meal for meal in results
        if meal.get("from_date", "")[:10] == target_date
    ]


class TandoorDaySensor(TandoorEntity, SensorEntity):
    """Sensor für ein bestimmtes Datum (heute/morgen/übermorgen)."""

    def __init__(
        self,
        coordinator: TandoorDataUpdateCoordinator,
        entry_id: str,
        day_key: str,
        day_offset: int,
        unique_id_suffix: str,
        name: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, entry_id)
        self._day_offset = day_offset
        self._attr_unique_id = f"{entry_id}_{unique_id_suffix}"
        self._attr_name = name
        self._attr_icon = "mdi:food"

    def _get_primary_meal(self) -> dict | None:
        meals = _get_meals_for_day(self.coordinator, self._day_offset)
        return meals[0] if meals else None

    def _make_absolute_url(self, url: str | None) -> str | None:
        """Sicherstellen, dass Bild-URLs absolut sind (HA braucht http://...)."""
        if not url:
            return None
        if url.startswith("http://") or url.startswith("https://"):
            return url
        # Relativer Pfad → Tandoor-Basis-URL voranstellen
        base = self.coordinator.base_url
        return f"{base}{url if url.startswith('/') else '/' + url}"

    @property
    def state(self) -> str:
        meal = self._get_primary_meal()
        if not meal:
            return "Nichts geplant"
        recipe = meal.get("recipe") or {}
        return recipe.get("name") or meal.get("recipe_name") or meal.get("title") or "Unbekannt"

    @property
    def entity_picture(self) -> str | None:
        meal = self._get_primary_meal()
        if not meal:
            return None
        recipe = meal.get("recipe") or {}
        return self._make_absolute_url(recipe.get("image"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        meal = self._get_primary_meal()
        if not meal:
            return {}
        recipe = meal.get("recipe") or {}
        meal_type = meal.get("meal_type") or {}
        return {
            "image_url": self._make_absolute_url(recipe.get("image")),
            "recipe_id": recipe.get("id"),
            "meal_type": meal_type.get("name") if isinstance(meal_type, dict) else meal.get("meal_type_name"),
            "servings": meal.get("servings"),
            "from_date": meal.get("from_date"),
            "all_meals_today": [
                {
                    "name": (m.get("recipe") or {}).get("name") or m.get("title", ""),
                    "meal_type": (m.get("meal_type") or {}).get("name") if isinstance(m.get("meal_type"), dict) else "",
                }
                for m in _get_meals_for_day(self.coordinator, self._day_offset)
            ],
        }


class TandoorNextMealsSensor(TandoorEntity, SensorEntity):
    """Sensor mit den nächsten geplanten Gerichten (heute + Zukunft)."""

    def __init__(self, coordinator: TandoorDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{SENSOR_NAECHSTE}"
        self._attr_name = "Tandoor Nächste Gerichte"
        self._attr_icon = "mdi:calendar-food"

    def _get_upcoming(self) -> list[dict]:
        from datetime import date
        today = date.today().isoformat()
        results = self.coordinator.data.get("meal_plan", {}).get("results", [])
        upcoming = [m for m in results if m.get("from_date", "")[:10] >= today]
        upcoming.sort(key=lambda m: m.get("from_date", ""))
        return upcoming

    @property
    def state(self) -> int:
        return len(self._get_upcoming())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        meals = self._get_upcoming()
        names = [
            (m.get("recipe") or {}).get("name") or m.get("title", "Unbekannt")
            for m in meals
        ]
        return {
            "meals_summary": ", ".join(names),
            "meals": [
                {
                    "name": (m.get("recipe") or {}).get("name") or m.get("title", "Unbekannt"),
                    "date": m.get("from_date", "")[:10],
                    "image_url": (m.get("recipe") or {}).get("image"),
                }
                for m in meals
            ],
        }


class TandoorShoppingSensor(TandoorEntity, SensorEntity):
    """Sensor für die Tandoor Shopping-Liste."""

    def __init__(self, coordinator: TandoorDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{SENSOR_ZUTATEN}"
        self._attr_name = "Tandoor Zutaten"
        self._attr_icon = "mdi:cart"

    def _get_unchecked(self) -> list[dict]:
        results = self.coordinator.data.get("shopping", {}).get("results", [])
        return [item for item in results if not item.get("checked", False)]

    @property
    def state(self) -> int:
        return len(self._get_unchecked())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self._get_unchecked()
        items_with_amounts = []
        for item in items:
            food = item.get("food") or {}
            name = food.get("name", "Unbekannt")
            amount = item.get("amount")
            unit = item.get("unit") or {}
            unit_name = unit.get("name", "")
            if amount:
                items_with_amounts.append(f"{name} {amount} {unit_name}".strip())
            else:
                items_with_amounts.append(name)
        return {
            "items_with_amounts": items_with_amounts,
            "raw_items": items,
        }


class TandoorInstalledVersionSensor(TandoorEntity, SensorEntity):
    """Sensor für die installierte Tandoor Docker-Version."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TandoorDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{SENSOR_INSTALLED_VERSION}"
        self._attr_name = "Tandoor Installierte Version"
        self._attr_icon = "mdi:package"

    @property
    def state(self) -> str:
        return self.coordinator.data.get("installed_version") or "Unbekannt"


class TandoorLatestVersionSensor(TandoorEntity, SensorEntity):
    """Sensor für die neueste Tandoor-Version (GitHub)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TandoorDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{SENSOR_LATEST_VERSION}"
        self._attr_name = "Tandoor Neueste Version"
        self._attr_icon = "mdi:package-up"

    @property
    def state(self) -> str:
        release = self.coordinator.data.get("latest_release")
        if not release:
            return "Unbekannt"
        return release.get("tag_name", "Unbekannt").lstrip("v")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        release = self.coordinator.data.get("latest_release") or {}
        return {
            "tag_name": release.get("tag_name"),
            "published_at": release.get("published_at"),
            "html_url": release.get("html_url"),
        }


class TandoorUpdateStatusSensor(TandoorEntity, SensorEntity):
    """Sensor für den Update-Status von Tandoor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TandoorDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{SENSOR_UPDATE_STATUS}"
        self._attr_name = "Tandoor Update Status"
        self._attr_icon = "mdi:update"

    def _get_versions(self) -> tuple[str | None, str | None]:
        installed = self.coordinator.data.get("installed_version")
        release = self.coordinator.data.get("latest_release") or {}
        latest_raw = release.get("tag_name", "")
        latest = latest_raw.lstrip("v") if latest_raw else None
        return installed, latest

    @property
    def state(self) -> str:
        installed, latest = self._get_versions()
        if not latest:
            return "Unbekannt"
        if not installed:
            return "update_available"  # konservativ: keine lokale Version = assume veraltet
        if installed == latest:
            return "up_to_date"
        return "update_available"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        installed, latest = self._get_versions()
        release = self.coordinator.data.get("latest_release") or {}
        published = release.get("published_at", "")
        # Format date nicely if possible
        release_date_str = ""
        if published:
            try:
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                release_date_str = dt.strftime("%d.%m.%Y %H:%M Uhr")
            except ValueError:
                release_date_str = published

        status_text = ""
        if installed and latest:
            if installed == latest:
                status_text = f"✅ Aktuell: {installed}"
            else:
                status_text = f"⬆️ Update verfügbar: {installed} → {latest}"
        elif latest:
            status_text = f"⬆️ Neueste Version: {latest}"

        return {
            "installed_version": installed,
            "latest_version": latest,
            "release_date": release_date_str,
            "release_url": release.get("html_url"),
            "status_text": status_text,
        }


class TandoorBackupStatusSensor(TandoorEntity, SensorEntity):
    """Sensor für den Backup-Status (Proxmox)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TandoorDataUpdateCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{SENSOR_BACKUP_STATUS}"
        self._attr_name = "Tandoor Backup Status"
        self._attr_icon = "mdi:backup-restore"

    @property
    def state(self) -> str:
        backup = self.coordinator.data.get("backup_status")
        if not backup:
            return "Kein Backup gefunden"
        return backup.get("filename", "Unbekannt")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        backup = self.coordinator.data.get("backup_status") or {}
        filename = backup.get("filename", "")
        backup_date_str = ""

        # Parse date from filename: vzdump-lxc-202-2026_02_17-03_00_03.tar.zst
        if filename:
            try:
                parts = filename.replace("vzdump-lxc-", "").split("-")
                # parts[1] = container_id, parts[2] = date, parts[3] = time
                date_part = parts[2]  # 2026_02_17
                time_part = parts[3].split(".")[0]  # 03_00_03
                dt_str = f"{date_part}-{time_part}".replace("_", "")
                dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
                backup_date_str = dt.strftime("%d.%m.%Y %H:%M Uhr")
            except (IndexError, ValueError):
                backup_date_str = ""

        return {
            "backup_date": backup_date_str,
            "backup_path": backup.get("path", ""),
        }
