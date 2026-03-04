"""DataUpdateCoordinator for Tandoor Recipes."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    API_MEAL_PLAN,
    API_SHOPPING,
    GITHUB_RELEASES_URL,
    CONF_TANDOOR_URL,
    CONF_API_TOKEN,
    CONF_SPACE_ID,
    CONF_UPDATE_INTERVAL,
    CONF_ENABLE_VERSION_CHECK,
    CONF_ENABLE_BACKUP,
    CONF_ENABLE_DOCKER_VERSION,
    CONF_PROXMOX_HOST,
    CONF_CONTAINER_ID,
    CONF_SSH_USER,
    CONF_SSH_PASSWORD,
    CONF_SSH_KEY,
)

_LOGGER = logging.getLogger(__name__)


class TandoorDataUpdateCoordinator(DataUpdateCoordinator):
    """Koordiniert alle API-Calls zu Tandoor."""

    def __init__(self, hass: HomeAssistant, session: aiohttp.ClientSession, config: dict) -> None:
        """Initialize the coordinator."""
        self.config = config
        self.session = session
        self._base_url = config[CONF_TANDOOR_URL].rstrip("/")
        self._token = config[CONF_API_TOKEN]
        self._space_id = config.get(CONF_SPACE_ID, 1)
        self._headers = {"Authorization": f"Bearer {self._token}"}

        super().__init__(
            hass,
            _LOGGER,
            name="Tandoor",
            update_interval=timedelta(seconds=config.get(CONF_UPDATE_INTERVAL, 300)),
        )

    @property
    def headers(self) -> dict:
        return self._headers

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def device_info(self) -> DeviceInfo:
        """Geräteinformation – bündelt alle Sensoren unter einem Eintrag in der HA-UI."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._base_url)},
            name="Tandoor Recipes",
            manufacturer="TandoorRecipes",
            model="Tandoor",
            configuration_url=self._base_url,
            # sw_version wird zur Laufzeit aus dem Coordinator-Data befüllt
            # (siehe TandoorLatestVersionSensor), hier erstmal statisch
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from all Tandoor APIs."""
        data: dict[str, Any] = {}

        # Meal plan
        try:
            data["meal_plan"] = await self._fetch_meal_plan()
        except Exception as err:
            _LOGGER.warning("Meal plan fetch failed: %s", err)
            data["meal_plan"] = {"results": []}

        # Shopping list
        try:
            data["shopping"] = await self._fetch_shopping()
        except Exception as err:
            _LOGGER.warning("Shopping fetch failed: %s", err)
            data["shopping"] = {"results": []}

        # Version check (GitHub)
        if self.config.get(CONF_ENABLE_VERSION_CHECK, True):
            try:
                data["latest_release"] = await self._fetch_latest_release()
            except Exception as err:
                _LOGGER.warning("GitHub release fetch failed: %s", err)
                data["latest_release"] = None
        else:
            data["latest_release"] = None

        # Installed Docker version (via SSH)
        if self.config.get(CONF_ENABLE_DOCKER_VERSION, False):
            try:
                data["installed_version"] = await self._fetch_installed_version()
            except Exception as err:
                _LOGGER.warning("Docker version fetch failed: %s", err)
                data["installed_version"] = None
        else:
            data["installed_version"] = None

        # Backup status (via SSH)
        if self.config.get(CONF_ENABLE_BACKUP, False):
            try:
                data["backup_status"] = await self._fetch_backup_status()
            except Exception as err:
                _LOGGER.warning("Backup status fetch failed: %s", err)
                data["backup_status"] = None
        else:
            data["backup_status"] = None

        return data

    async def _fetch_meal_plan(self) -> dict:
        """Fetch meal plan from Tandoor API – alle Eintraege ab heute via Paginierung."""
        from datetime import date, timedelta
        from_date = (date.today() - timedelta(days=1)).isoformat()
        to_date = (date.today() + timedelta(days=14)).isoformat()

        all_results = []
        url = (
            f"{self._base_url}{API_MEAL_PLAN}?format=json"
            f"&from_date={from_date}&to_date={to_date}&page_size=100"
        )

        while url:
            async with self.session.get(
                url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 401:
                    raise UpdateFailed("Invalid API token (401 Unauthorized)")
                if resp.status == 403:
                    raise UpdateFailed(
                        f"Permission denied (403). Check that space_id={self._space_id} is correct."
                    )
                resp.raise_for_status()
                data = await resp.json()
                all_results.extend(data.get("results", []))
                url = data.get("next")

        return {"results": all_results, "count": len(all_results)}

    async def _fetch_shopping(self) -> dict:
        """Fetch shopping list entries from Tandoor API."""
        url = f"{self._base_url}{API_SHOPPING}?format=json"
        async with self.session.get(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _fetch_latest_release(self) -> dict | None:
        """Fetch latest release from GitHub API."""
        async with self.session.get(GITHUB_RELEASES_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

    async def _fetch_installed_version(self) -> str | None:
        """Fetch installed Docker image version via SSH."""
        try:
            import asyncssh
        except ImportError:
            _LOGGER.error("asyncssh not installed, cannot check Docker version")
            return None

        host = self.config.get(CONF_PROXMOX_HOST)
        container_id = self.config.get(CONF_CONTAINER_ID)
        user = self.config.get(CONF_SSH_USER, "root")
        password = self.config.get(CONF_SSH_PASSWORD)
        key = self.config.get(CONF_SSH_KEY)

        cmd = (
            f"pct exec {container_id} -- docker inspect vabene1111/recipes:latest "
            f"--format='{{{{index .Config.Labels \"org.opencontainers.image.version\"}}}}'"
        )

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
                result = await conn.run(cmd, check=True)
                version = result.stdout.strip().strip("'")
                return version if version else None
        except Exception as err:
            _LOGGER.warning("SSH error fetching installed version: %s", err)
            return None

    async def _fetch_backup_status(self) -> dict | None:
        """Fetch latest backup file info via SSH."""
        try:
            import asyncssh
        except ImportError:
            _LOGGER.error("asyncssh not installed, cannot check backup status")
            return None

        host = self.config.get(CONF_PROXMOX_HOST)
        container_id = self.config.get(CONF_CONTAINER_ID)
        user = self.config.get(CONF_SSH_USER, "root")
        password = self.config.get(CONF_SSH_PASSWORD)
        key = self.config.get(CONF_SSH_KEY)

        cmd = f"ls -t /var/lib/vz/dump/vzdump-lxc-{container_id}-*.tar.zst 2>/dev/null | head -1"

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
                result = await conn.run(cmd, check=True)
                path = result.stdout.strip()
                if not path:
                    return None
                filename = path.split("/")[-1]
                return {"path": path, "filename": filename}
        except Exception as err:
            _LOGGER.warning("SSH error fetching backup status: %s", err)
            return None

    async def async_patch_shopping_item(self, item_id: int, checked: bool) -> bool:
        """Mark a shopping list item as checked/unchecked."""
        url = f"{self._base_url}{API_SHOPPING}{item_id}/"
        payload = {"checked": checked}
        try:
            async with self.session.patch(
                url,
                headers={**self._headers, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status in (200, 204)
        except Exception as err:
            _LOGGER.error("Failed to patch shopping item %s: %s", item_id, err)
            return False

    async def async_validate_connection(self) -> str | None:
        """Test connection to Tandoor API. Returns error string or None if OK."""
        try:
            await self._fetch_meal_plan()
            return None
        except UpdateFailed as err:
            return str(err)
        except aiohttp.ClientConnectorError:
            return "Cannot connect to Tandoor. Check the URL."
        except aiohttp.ClientResponseError as err:
            return f"HTTP error {err.status}"
        except Exception as err:
            return f"Unexpected error: {err}"
