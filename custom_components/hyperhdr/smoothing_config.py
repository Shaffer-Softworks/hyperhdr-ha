"""Helpers for HyperHDR v22 smoothing config (config get/set)."""

from __future__ import annotations

import logging
from typing import Any

from hyperhdr import client

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_INSTANCE_CLIENTS,
    CONF_SMOOTHING_CONFIGS,
    DOMAIN,
    SIGNAL_SMOOTHING_CONFIG,
)


def _device_id(server_id: str, instance_num: int) -> str:
    return f"{server_id}_{instance_num}"


_LOGGER = logging.getLogger(__name__)


async def async_ensure_config_auth(
    hyperhdr_client: client.HyperHDRClient,
    *,
    admin_password: str | None,
) -> bool:
    """Ensure the client can call config get/set.

    Tries getconfig first. If authorization is required and an admin password
    is configured, logs in with that password and retries.
    """
    response = await hyperhdr_client.async_get_config()
    if client.ResponseOK(response):
        return True

    error = (response or {}).get("error") if isinstance(response, dict) else None
    needs_auth = isinstance(error, str) and "authorization" in error.lower()
    if not needs_auth or not admin_password:
        _LOGGER.debug(
            "HyperHDR config getconfig failed (auth_needed=%s, password_set=%s): %s",
            needs_auth,
            bool(admin_password),
            error,
        )
        return False

    login_resp = await hyperhdr_client.async_login(password=admin_password)
    if not client.LoginResponseOK(login_resp):
        _LOGGER.warning(
            "HyperHDR admin password login failed; smoothing config controls "
            "will be unavailable"
        )
        return False

    response = await hyperhdr_client.async_get_config()
    if client.ResponseOK(response):
        return True

    _LOGGER.warning(
        "HyperHDR config getconfig still failed after admin login: %s",
        (response or {}).get("error") if isinstance(response, dict) else None,
    )
    return False


async def async_load_smoothing_config(
    hyperhdr_client: client.HyperHDRClient,
    *,
    admin_password: str | None,
) -> dict[str, Any] | None:
    """Authenticate if needed and return the smoothing config object."""
    if not await async_ensure_config_auth(
        hyperhdr_client, admin_password=admin_password
    ):
        return None
    return await hyperhdr_client.async_get_smoothing_config()


async def async_patch_smoothing_config(
    hass: HomeAssistant,
    entry_id: str,
    server_id: str,
    instance_num: int,
    **fields: Any,
) -> bool:
    """Merge-patch smoothing config and notify entities."""
    entry_data = hass.data[DOMAIN][entry_id]
    hyperhdr_client: client.HyperHDRClient = entry_data[CONF_INSTANCE_CLIENTS][
        instance_num
    ]
    updated = await hyperhdr_client.async_update_smoothing_config(**fields)
    if updated is None:
        _LOGGER.warning(
            "Failed to update HyperHDR smoothing config fields %s",
            list(fields),
        )
        return False

    entry_data.setdefault(CONF_SMOOTHING_CONFIGS, {})[instance_num] = updated
    async_dispatcher_send(
        hass,
        SIGNAL_SMOOTHING_CONFIG.format(_device_id(server_id, instance_num)),
    )
    return True


def smoothing_config_available(entry_data: dict[str, Any], instance_num: int) -> bool:
    """Return True when smoothing config was loaded for this instance."""
    configs = entry_data.get(CONF_SMOOTHING_CONFIGS) or {}
    return instance_num in configs and configs[instance_num] is not None
