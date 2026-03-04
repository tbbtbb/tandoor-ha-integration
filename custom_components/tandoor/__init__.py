"""Tandoor Recipes Home Assistant Integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.aiohttp_client as aiohttp_helper

from .const import (
    DOMAIN,
    PLATFORMS,
    DATA_COORDINATOR,
    DATA_CONFIG,
    DATA_READY_TO_SYNC,
    DATA_BRING_ENTITY,
    CONF_ENABLE_BRING,
    CONF_BRING_ENTITY,
    SERVICE_LOAD,
    SERVICE_SYNC,
    SERVICE_RESET,
)
from .coordinator import TandoorDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tandoor from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Options überschreiben data – so wirken Änderungen via "Konfigurieren" sofort
    effective_config = {**entry.data, **entry.options}

    session = aiohttp_helper.async_get_clientsession(hass)
    coordinator = TandoorDataUpdateCoordinator(hass, session, effective_config)

    # First refresh
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_CONFIG: effective_config,
        DATA_READY_TO_SYNC: False,
        DATA_BRING_ENTITY: effective_config.get(CONF_BRING_ENTITY, "todo.zuhause"),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    _register_services(hass, entry)

    # Automatischer Reload wenn Options geändert werden
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Remove services if no more entries
    if not hass.data[DOMAIN]:
        for service in (SERVICE_LOAD, SERVICE_SYNC, SERVICE_RESET):
            hass.services.async_remove(DOMAIN, service)

    return unload_ok


def _register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register integration services."""

    async def handle_load_from_tandoor(call: ServiceCall) -> None:
        """Force refresh data from Tandoor and show a summary notification."""
        coordinator: TandoorDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

        await coordinator.async_refresh()
        await asyncio.sleep(1)

        meal_count = len(
            [
                m
                for m in coordinator.data.get("meal_plan", {}).get("results", [])
                if True  # all meals
            ]
        )
        shopping_count = len(
            [
                i
                for i in coordinator.data.get("shopping", {}).get("results", [])
                if not i.get("checked", False)
            ]
        )

        hass.data[DOMAIN][entry.entry_id][DATA_READY_TO_SYNC] = True

        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "🍽️ Tandoor geladen",
                "message": (
                    f"**Gerichte geplant:** {meal_count}\n"
                    f"**Zutaten auf Einkaufsliste:** {shopping_count}\n\n"
                    "Bereit zum Sync mit Bring! ✅"
                ),
                "notification_id": "tandoor_load_status",
            },
        )

    async def handle_sync_to_bring(call: ServiceCall) -> None:
        """Sync unchecked Tandoor shopping items to Bring!."""
        entry_data = hass.data[DOMAIN][entry.entry_id]
        coordinator: TandoorDataUpdateCoordinator = entry_data[DATA_COORDINATOR]
        bring_entity = entry_data[DATA_BRING_ENTITY]
        config = entry_data[DATA_CONFIG]

        if not config.get(CONF_ENABLE_BRING, False):
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "❌ Bring! nicht aktiviert",
                    "message": "Bring! Integration ist in den Einstellungen nicht aktiviert.",
                    "notification_id": "tandoor_sync_status",
                },
            )
            return

        # Get unchecked Tandoor items
        raw_shopping = coordinator.data.get("shopping", {}).get("results", [])
        unchecked = [i for i in raw_shopping if not i.get("checked", False)]

        if not unchecked:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "ℹ️ Keine Zutaten",
                    "message": "Keine ungecheckten Zutaten in Tandoor gefunden.",
                    "notification_id": "tandoor_sync_status",
                },
            )
            return

        # Get existing Bring! items
        bring_state = hass.states.get(bring_entity)
        bring_items: list[str] = []
        if bring_state and bring_state.attributes.get("items"):
            bring_items = [
                item.get("summary", "").lower()
                for item in bring_state.attributes["items"]
            ]

        # Filter duplicates using fuzzy match
        new_items: list[dict[str, Any]] = []
        for item in unchecked:
            food = item.get("food") or {}
            food_name = food.get("name", "")
            if not food_name:
                continue

            food_lower = food_name.lower()
            already_in_bring = any(
                food_lower in bring_item or bring_item in food_lower
                for bring_item in bring_items
            )

            if not already_in_bring:
                amount = item.get("amount")
                unit = item.get("unit") or {}
                unit_name = unit.get("name", "")
                description = f"{amount} {unit_name}".strip() if amount else ""
                new_items.append({
                    "id": item.get("id"),
                    "name": food_name,
                    "description": description,
                })

        if not new_items:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "✅ Bring! Sync",
                    "message": "Alle Zutaten sind bereits in Bring! vorhanden.",
                    "notification_id": "tandoor_sync_status",
                },
            )
            return

        # Add to Bring!
        failed_bring = 0
        for item in new_items:
            try:
                await hass.services.async_call(
                    "todo",
                    "add_item",
                    {
                        "entity_id": bring_entity,
                        "item": item["name"],
                        "description": item["description"],
                    },
                    blocking=True,
                )
            except Exception as err:
                _LOGGER.error("Failed to add '%s' to Bring!: %s", item["name"], err)
                failed_bring += 1
            await asyncio.sleep(0.3)

        # Mark as checked in Tandoor
        failed_patch = 0
        for item in new_items:
            if item.get("id") is not None:
                ok = await coordinator.async_patch_shopping_item(item["id"], checked=True)
                if not ok:
                    failed_patch += 1
            await asyncio.sleep(0.2)

        # Refresh sensor
        await coordinator.async_refresh()

        added = len(new_items) - failed_bring
        msg = f"**{added} Zutaten** zu Bring! hinzugefügt! ✅"
        if failed_bring:
            msg += f"\n⚠️ {failed_bring} Fehler beim Hinzufügen."
        if failed_patch:
            msg += f"\n⚠️ {failed_patch} Items konnten nicht in Tandoor abgehakt werden."

        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "✅ Bring! Sync",
                "message": msg,
                "notification_id": "tandoor_sync_status",
            },
        )

    async def handle_reset_status(call: ServiceCall) -> None:
        """Reset internal sync state."""
        hass.data[DOMAIN][entry.entry_id][DATA_READY_TO_SYNC] = False
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "🔄 Tandoor Reset",
                "message": "Sync-Status wurde zurückgesetzt.",
                "notification_id": "tandoor_reset_status",
            },
        )

    hass.services.async_register(DOMAIN, SERVICE_LOAD, handle_load_from_tandoor)
    hass.services.async_register(DOMAIN, SERVICE_SYNC, handle_sync_to_bring)
    hass.services.async_register(DOMAIN, SERVICE_RESET, handle_reset_status)
