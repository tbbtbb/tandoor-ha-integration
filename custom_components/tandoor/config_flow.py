"""Config Flow for Tandoor Recipes integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.aiohttp_client as aiohttp_helper

from .const import (
    DOMAIN,
    CONF_TANDOOR_URL,
    CONF_API_TOKEN,
    CONF_SPACE_ID,
    CONF_UPDATE_INTERVAL,
    CONF_ENABLE_BRING,
    CONF_BRING_ENTITY,
    CONF_AUTO_SYNC,
    CONF_ENABLE_BACKUP,
    CONF_PROXMOX_HOST,
    CONF_CONTAINER_ID,
    CONF_SSH_USER,
    CONF_SSH_PASSWORD,
    CONF_SSH_KEY,
    CONF_ENABLE_VERSION_CHECK,
    CONF_ENABLE_DOCKER_VERSION,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_SPACE_ID,
    DEFAULT_PROXMOX_HOST,
    DEFAULT_CONTAINER_ID,
    DEFAULT_SSH_USER,
)

_LOGGER = logging.getLogger(__name__)


class TandoorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Tandoor Recipes config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Tandoor Connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            # Validate connection
            error = await self._test_tandoor_connection(
                user_input[CONF_TANDOOR_URL],
                user_input[CONF_API_TOKEN],
                user_input.get(CONF_SPACE_ID, DEFAULT_SPACE_ID),
            )
            if error:
                errors["base"] = error
            else:
                return await self.async_step_bring()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_TANDOOR_URL, default="http://192.168.178.124:8090"): str,
                vol.Required(CONF_API_TOKEN): str,
                vol.Optional(CONF_SPACE_ID, default=DEFAULT_SPACE_ID): int,
                vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
                    int, vol.Range(min=60, max=3600)
                ),
            }),
            errors=errors,
            description_placeholders={
                "api_path": "/api/user-token-create/",
            },
        )

    async def async_step_bring(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Bring! Integration (optional)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_backup()

        return self.async_show_form(
            step_id="bring",
            data_schema=vol.Schema({
                vol.Optional(CONF_ENABLE_BRING, default=False): bool,
                vol.Optional(CONF_BRING_ENTITY, default="todo.zuhause"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="todo")
                ),
                vol.Optional(CONF_AUTO_SYNC, default=False): bool,
            }),
            errors=errors,
        )

    async def async_step_backup(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Backup Monitoring (optional)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)

            # Test SSH if backup monitoring is enabled
            if user_input.get(CONF_ENABLE_BACKUP, False):
                error = await self._test_ssh_connection(user_input)
                if error:
                    errors["base"] = error

            if not errors:
                return await self.async_step_versions()

        return self.async_show_form(
            step_id="backup",
            data_schema=vol.Schema({
                vol.Optional(CONF_ENABLE_BACKUP, default=False): bool,
                vol.Optional(CONF_PROXMOX_HOST, default=DEFAULT_PROXMOX_HOST): str,
                vol.Optional(CONF_CONTAINER_ID, default=DEFAULT_CONTAINER_ID): int,
                vol.Optional(CONF_SSH_USER, default=DEFAULT_SSH_USER): str,
                vol.Optional(CONF_SSH_PASSWORD): str,
                vol.Optional(CONF_SSH_KEY): str,
            }),
            errors=errors,
        )

    async def async_step_versions(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4: Version Monitoring (optional)."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="Tandoor Recipes",
                data=self._data,
            )

        return self.async_show_form(
            step_id="versions",
            data_schema=vol.Schema({
                vol.Optional(CONF_ENABLE_VERSION_CHECK, default=True): bool,
                vol.Optional(CONF_ENABLE_DOCKER_VERSION, default=False): bool,
            }),
        )

    async def _test_tandoor_connection(
        self, url: str, token: str, space_id: int
    ) -> str | None:
        """Test the Tandoor connection. Returns error key or None."""
        session = aiohttp_helper.async_get_clientsession(self.hass)
        test_url = f"{url.rstrip('/')}/api/meal-plan/?format=json&space={space_id}"
        headers = {"Authorization": f"Token {token}"}
        try:
            async with session.get(
                test_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return None
                if resp.status == 401:
                    return "invalid_token"
                if resp.status == 403:
                    return "invalid_space"
                return "cannot_connect"
        except aiohttp.ClientConnectorError:
            return "cannot_connect"
        except Exception:
            return "cannot_connect"

    async def _test_ssh_connection(self, config: dict) -> str | None:
        """Test SSH connection for backup monitoring. Returns error key or None."""
        try:
            import asyncssh
        except ImportError:
            return "asyncssh_missing"

        host = config.get(CONF_PROXMOX_HOST)
        user = config.get(CONF_SSH_USER, "root")
        password = config.get(CONF_SSH_PASSWORD)
        key = config.get(CONF_SSH_KEY)

        connect_kwargs: dict = {
            "host": host,
            "username": user,
            "known_hosts": None,
        }
        if password:
            connect_kwargs["password"] = password
        if key:
            connect_kwargs["client_keys"] = [key]

        try:
            async with asyncssh.connect(**connect_kwargs) as conn:
                await conn.run("echo ok", check=True)
            return None
        except asyncssh.PermissionDenied:
            return "ssh_auth_failed"
        except Exception:
            return "ssh_cannot_connect"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow."""
        return TandoorOptionsFlow(config_entry)


class TandoorOptionsFlow(config_entries.OptionsFlow):
    """Options flow – alle wichtigen Parameter nachträglich änderbar."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._base_data: dict[str, Any] = {}

    def _current(self, key: str, default=None):
        """Aktuellen Wert aus options (Vorrang) oder data holen."""
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )

    async def async_step_init(self, user_input=None):
        """Schritt 1: Tandoor-Verbindung – URL, Token, Space, Intervall."""
        errors: dict[str, str] = {}

        if user_input is not None:
            new_url = user_input[CONF_TANDOOR_URL]
            new_token = user_input[CONF_API_TOKEN]
            new_space = user_input.get(CONF_SPACE_ID, DEFAULT_SPACE_ID)

            session = aiohttp_helper.async_get_clientsession(self.hass)
            test_url = f"{new_url.rstrip('/')}/api/meal-plan/?format=json&space={new_space}"
            headers = {"Authorization": f"Token {new_token}"}
            try:
                async with session.get(
                    test_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 401:
                        errors["base"] = "invalid_token"
                    elif resp.status == 403:
                        errors["base"] = "invalid_space"
                    elif resp.status != 200:
                        errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"

            if not errors:
                self._base_data = dict(user_input)
                return await self.async_step_features()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_TANDOOR_URL,
                    default=self._current(CONF_TANDOOR_URL, "http://192.168.178.124:8090"),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                ),
                vol.Required(
                    CONF_API_TOKEN,
                    default=self._current(CONF_API_TOKEN, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_SPACE_ID,
                    default=self._current(CONF_SPACE_ID, DEFAULT_SPACE_ID),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=99, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=self._current(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=60, max=3600, step=60,
                        mode=selector.NumberSelectorMode.SLIDER,
                        unit_of_measurement="s",
                    )
                ),
            }),
            errors=errors,
        )

    async def async_step_features(self, user_input=None):
        """Schritt 2: Features an/aus & Bring!-Entität."""
        if user_input is not None:
            self._base_data.update(user_input)
            # Wenn Backup aktiviert: weiter zu SSH-Schritt
            if user_input.get(CONF_ENABLE_BACKUP, False) or user_input.get(CONF_ENABLE_DOCKER_VERSION, False):
                return await self.async_step_ssh()
            # Sonst direkt speichern
            return self.async_create_entry(title="", data=self._base_data)

        return self.async_show_form(
            step_id="features",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_ENABLE_BRING,
                    default=self._current(CONF_ENABLE_BRING, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_BRING_ENTITY,
                    default=self._current(CONF_BRING_ENTITY, "todo.zuhause"),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="todo")
                ),
                vol.Optional(
                    CONF_ENABLE_VERSION_CHECK,
                    default=self._current(CONF_ENABLE_VERSION_CHECK, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ENABLE_BACKUP,
                    default=self._current(CONF_ENABLE_BACKUP, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ENABLE_DOCKER_VERSION,
                    default=self._current(CONF_ENABLE_DOCKER_VERSION, False),
                ): selector.BooleanSelector(),
            }),
        )

    async def async_step_ssh(self, user_input=None):
        """Schritt 3 (optional): SSH-Credentials für Backup & Docker-Version."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # SSH testen
            error = await self._test_ssh(user_input)
            if error:
                errors["base"] = error
            else:
                self._base_data.update(user_input)
                return self.async_create_entry(title="", data=self._base_data)

        return self.async_show_form(
            step_id="ssh",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_PROXMOX_HOST,
                    default=self._current(CONF_PROXMOX_HOST, DEFAULT_PROXMOX_HOST),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(
                    CONF_CONTAINER_ID,
                    default=self._current(CONF_CONTAINER_ID, DEFAULT_CONTAINER_ID),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=100, max=999, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_SSH_USER,
                    default=self._current(CONF_SSH_USER, DEFAULT_SSH_USER),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(
                    CONF_SSH_PASSWORD,
                    default=self._current(CONF_SSH_PASSWORD, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_SSH_KEY,
                    default=self._current(CONF_SSH_KEY, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
            }),
            errors=errors,
        )

    async def _test_ssh(self, config: dict) -> str | None:
        """SSH-Verbindung testen. Gibt Fehler-Key zurück oder None."""
        try:
            import asyncssh
        except ImportError:
            return "asyncssh_missing"

        connect_kwargs: dict = {
            "host": config.get(CONF_PROXMOX_HOST),
            "username": config.get(CONF_SSH_USER, "root"),
            "known_hosts": None,
        }
        password = config.get(CONF_SSH_PASSWORD)
        key = config.get(CONF_SSH_KEY)
        if password:
            connect_kwargs["password"] = password
        if key:
            connect_kwargs["client_keys"] = [key]

        try:
            async with asyncssh.connect(**connect_kwargs) as conn:
                await conn.run("echo ok", check=True)
            return None
        except asyncssh.PermissionDenied:
            return "ssh_auth_failed"
        except Exception:
            return "ssh_cannot_connect"
