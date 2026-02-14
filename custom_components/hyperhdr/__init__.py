"""The HyperHDR component."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
import inspect
import logging
from typing import Any, cast

from awesomeversion import AwesomeVersion
from hyperhdr import client, const as hyperhdr_const

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)


from .const import (
    CONF_INSTANCE_CLIENTS,
    CONF_ON_UNLOAD,
    CONF_ROOT_CLIENT,
    CONF_SYSINFO,
    DEFAULT_NAME,
    DOMAIN,
    HYPERHDR_RELEASES_URL,
    HYPERHDR_VERSION_WARN_CUTOFF,
    SIGNAL_INSTANCE_ADD,
    SIGNAL_INSTANCE_REMOVE,
    TYPE_HYPERHDR_NUMBER_BASE,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_DECAY,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_TIME,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_UPDATE_FREQ,
    TYPE_HYPERHDR_SELECT_BASE,
    TYPE_HYPERHDR_SELECT_SMOOTHING_TYPE,
)

### HyperHDR v0.0.8
PLATFORMS = [Platform.CAMERA, Platform.LIGHT, Platform.SWITCH, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]

### Disabled platforms (uncomment to enable specific ones)
# PLATFORMS = [Platform.LIGHT, Platform.SWITCH]

### Original - From Hyperion
# PLATFORMS = [Platform.CAMERA, Platform.LIGHT, Platform.SENSOR, Platform.SWITCH]

_LOGGER = logging.getLogger(__name__)

# Unique ID
# =========
# A config entry represents a connection to a single HyperHDR server. The config entry
# unique_id is the server id returned from the HyperHDR instance (a unique ID per
# server).
#
# Each server connection may create multiple entities. The unique_id for each entity is
# <server id>_<instance #>_<name>, where <server_id> will be the unique_id on the
# relevant config entry (as above), <instance #> will be the server instance # and
# <name> will be a unique identifying type name for each entity associated with this
# server/instance (e.g. "hyperhdr_light").
#
# The get_hyperhdr_unique_id method will create a per-entity unique id when given the
# server id, an instance number and a name.

# hass.data format
# ================
#
# hass.data[DOMAIN] = {
#     <config_entry.entry_id>: {
#         "ROOT_CLIENT": <HyperHDR Client>,
#         "ON_UNLOAD": [<callable>, ...],
#     }
# }


def get_hyperhdr_unique_id(server_id: str, instance: int, name: str) -> str:
    """Get a unique_id for a HyperHDR instance."""
    return f"{server_id}_{instance}_{name}"


def get_hyperhdr_device_id(server_id: str, instance: int) -> str:
    """Get an id for a HyperHDR device/instance."""
    return f"{server_id}_{instance}"


def split_hyperhdr_unique_id(unique_id: str) -> tuple[str, int, str] | None:
    """Split a unique_id into a (server_id, instance, type) tuple."""
    data = tuple(unique_id.split("_", 2))
    if len(data) != 3:
        return None
    try:
        return (data[0], int(data[1]), data[2])
    except ValueError:
        return None


def create_hyperhdr_client(
    *args: Any,
    **kwargs: Any,
) -> client.HyperHDRClient:
    """Create a HyperHDR Client."""
    if kwargs:
        try:
            signature = inspect.signature(client.HyperHDRClient)
        except (TypeError, ValueError):
            signature = None
        if signature is not None and not any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        ):
            supported = signature.parameters.keys()
            kwargs = {key: value for key, value in kwargs.items() if key in supported}
    while True:
        try:
            return client.HyperHDRClient(*args, **kwargs)
        except TypeError as exc:
            msg = str(exc)
            if "unexpected keyword argument" not in msg:
                raise
            if "'" not in msg:
                raise
            parts = msg.split("'")
            if len(parts) < 3:
                raise
            unexpected = parts[1]
            if unexpected not in kwargs:
                raise
            _LOGGER.debug(
                "Dropping unsupported HyperHDRClient argument: %s", unexpected
            )
            kwargs = {key: value for key, value in kwargs.items() if key != unexpected}


async def async_create_connect_hyperhdr_client(
    *args: Any,
    **kwargs: Any,
) -> client.HyperHDRClient | None:
    """Create and connect a HyperHDR Client."""
    hyperhdr_client = create_hyperhdr_client(*args, **kwargs)

    if not await hyperhdr_client.async_client_connect():
        return None
    return hyperhdr_client


@callback
def listen_for_instance_updates(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_func: Callable,
    remove_func: Callable,
) -> None:
    """Listen for instance additions/removals."""

    hass.data[DOMAIN][config_entry.entry_id][CONF_ON_UNLOAD].extend(
        [
            async_dispatcher_connect(
                hass,
                SIGNAL_INSTANCE_ADD.format(config_entry.entry_id),
                add_func,
            ),
            async_dispatcher_connect(
                hass,
                SIGNAL_INSTANCE_REMOVE.format(config_entry.entry_id),
                remove_func,
            ),
        ]
    )


# Entity unique-id suffixes for features that have been permanently removed.
# These are cleaned from the entity registry on every load so stale entries
# never linger in the UI.
_PERMANENTLY_REMOVED_SUFFIXES = (
    # Old JSON-API camera removed in v0.1.5.
    "hyperhdr_camera",
    # Color Engine select removed in v0.1.5.
    f"{TYPE_HYPERHDR_SELECT_BASE}_color_engine",
)

# Smoothing entity suffixes — removed from the registry when the connected
# HyperHDR server does not expose smoothing data.
_SMOOTHING_SUFFIXES = (
    f"{TYPE_HYPERHDR_NUMBER_BASE}_{TYPE_HYPERHDR_NUMBER_SMOOTHING_TIME}",
    f"{TYPE_HYPERHDR_NUMBER_BASE}_{TYPE_HYPERHDR_NUMBER_SMOOTHING_DECAY}",
    f"{TYPE_HYPERHDR_NUMBER_BASE}_{TYPE_HYPERHDR_NUMBER_SMOOTHING_UPDATE_FREQ}",
    f"{TYPE_HYPERHDR_SELECT_BASE}_{TYPE_HYPERHDR_SELECT_SMOOTHING_TYPE}",
)


def _async_cleanup_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Remove stale entity-registry entries left over from removed features.

    Permanently removed entities (old camera, color engine) are always pruned.
    Smoothing entities are pruned per-instance when the connected HyperHDR
    server does not expose smoothing data.
    """
    ent_reg = er.async_get(hass)
    instance_clients = hass.data[DOMAIN][entry.entry_id][CONF_INSTANCE_CLIENTS]

    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        uid = entity_entry.unique_id

        # Always remove permanently deleted features.
        if any(uid.endswith(f"_{suffix}") for suffix in _PERMANENTLY_REMOVED_SUFFIXES):
            _LOGGER.debug("Removing stale entity %s (%s)", entity_entry.entity_id, uid)
            ent_reg.async_remove(entity_entry.entity_id)
            continue

        # Remove smoothing entities for instances whose server lacks smoothing.
        if any(uid.endswith(f"_{suffix}") for suffix in _SMOOTHING_SUFFIXES):
            parts = split_hyperhdr_unique_id(uid)
            if parts is not None:
                _, instance_num, _ = parts
                inst_client = instance_clients.get(instance_num)
                if inst_client is not None and inst_client.smoothing is None:
                    _LOGGER.debug(
                        "Removing unsupported smoothing entity %s (%s)",
                        entity_entry.entity_id,
                        uid,
                    )
                    ent_reg.async_remove(entity_entry.entity_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a config entry to a newer version.

    Version 1 → 2: No data-schema changes; entity-registry cleanup of removed
    features (old camera, color engine, smoothing) is handled at load time in
    async_setup_entry.
    """
    _LOGGER.debug("Migrating config entry from version %s", entry.version)
    # No data transformations needed — just accept the bump.
    hass.config_entries.async_update_entry(entry, version=2)
    _LOGGER.debug("Migration to version 2 successful")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HyperHDR from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    token = entry.data.get(CONF_TOKEN)

    hyperhdr_client = await async_create_connect_hyperhdr_client(
        host, port, token=token, raw_connection=True
    )

    # Client won't connect? => Not ready.
    if not hyperhdr_client:
        raise ConfigEntryNotReady

    # Client needs authentication, but no token provided? => Reauth.
    auth_resp = await hyperhdr_client.async_is_auth_required()
    if (
        auth_resp is not None
        and client.ResponseOK(auth_resp)
        and auth_resp.get(hyperhdr_const.KEY_INFO, {}).get(
            hyperhdr_const.KEY_REQUIRED, False
        )
        and token is None
    ):
        await hyperhdr_client.async_client_disconnect()
        raise ConfigEntryAuthFailed

    # Client login doesn't work? => Reauth.
    if not await hyperhdr_client.async_client_login():
        await hyperhdr_client.async_client_disconnect()
        raise ConfigEntryAuthFailed

    # Now that we are authenticated, check the server version.
    version = await hyperhdr_client.async_sysinfo_version()
    if version is not None:
        with suppress(ValueError):
            if AwesomeVersion(version) < AwesomeVersion(HYPERHDR_VERSION_WARN_CUTOFF):
                _LOGGER.warning(
                    (
                        "Using a HyperHDR server version < %s is not recommended --"
                        " some features may be unavailable or may not function"
                        " correctly. Please consider upgrading: %s"
                    ),
                    HYPERHDR_VERSION_WARN_CUTOFF,
                    HYPERHDR_RELEASES_URL,
                )

    # Fetch full sysinfo for DeviceInfo (reuses the authenticated root client).
    sysinfo_resp = await hyperhdr_client.async_sysinfo()
    if sysinfo_resp is not None and client.ResponseOK(sysinfo_resp):
        sysinfo = sysinfo_resp.get(hyperhdr_const.KEY_INFO, {})
    else:
        sysinfo = {}

    # Cannot switch instance or cannot load state? => Not ready.
    if (
        not await hyperhdr_client.async_client_switch_instance()
        or not client.ServerInfoResponseOK(await hyperhdr_client.async_get_serverinfo())
    ):
        await hyperhdr_client.async_client_disconnect()
        raise ConfigEntryNotReady

    # We need 1 root client (to manage instances being removed/added) and then 1 client
    # per HyperHDR server instance which is shared for all entities associated with
    # that instance.
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        CONF_ROOT_CLIENT: hyperhdr_client,
        CONF_INSTANCE_CLIENTS: {},
        CONF_ON_UNLOAD: [],
        CONF_SYSINFO: sysinfo,
    }

    async def async_instances_to_clients(response: dict[str, Any]) -> None:
        """Convert instances to HyperHDR clients."""
        if not response or hyperhdr_const.KEY_DATA not in response:
            return
        await async_instances_to_clients_raw(response[hyperhdr_const.KEY_DATA])

    async def async_instances_to_clients_raw(instances: list[dict[str, Any]]) -> None:
        """Convert instances to HyperHDR clients."""
        device_registry = dr.async_get(hass)
        running_instances: set[int] = set()
        stopped_instances: set[int] = set()
        existing_instances = hass.data[DOMAIN][entry.entry_id][CONF_INSTANCE_CLIENTS]
        server_id = cast(str, entry.unique_id)

        sysinfo = hass.data[DOMAIN][entry.entry_id].get(CONF_SYSINFO, {})

        # In practice, an instance can be in 3 states as seen by this function:
        #
        #    * Exists, and is running: Should be present in HASS/registry.
        #    * Exists, but is not running: Cannot add it yet, but entity may have be
        #      registered from a previous time it was running.
        #    * No longer exists at all: Should not be present in HASS/registry.

        # Add instances that are missing.
        for instance in instances:
            instance_num = instance.get(hyperhdr_const.KEY_INSTANCE)
            if instance_num is None:
                continue
            if not instance.get(hyperhdr_const.KEY_RUNNING, False):
                stopped_instances.add(instance_num)
                continue
            running_instances.add(instance_num)
            if instance_num in existing_instances:
                continue
            hyperhdr_client = await async_create_connect_hyperhdr_client(
                host, port, instance=instance_num, token=token
            )
            if not hyperhdr_client:
                continue
            existing_instances[instance_num] = hyperhdr_client
            instance_name = instance.get(hyperhdr_const.KEY_FRIENDLY_NAME, DEFAULT_NAME)

            async_dispatcher_send(
                hass,
                SIGNAL_INSTANCE_ADD.format(entry.entry_id),
                instance_num,
                instance_name,
                sysinfo,
            )

        # Remove entities that are not running instances on HyperHDR.
        for instance_num in set(existing_instances) - running_instances:
            del existing_instances[instance_num]
            async_dispatcher_send(
                hass, SIGNAL_INSTANCE_REMOVE.format(entry.entry_id), instance_num
            )

        # Ensure every device associated with this config entry is still in the list of
        # motionEye cameras, otherwise remove the device (and thus entities).
        known_devices = {
            get_hyperhdr_device_id(server_id, instance_num)
            for instance_num in running_instances | stopped_instances
        }
        for device_entry in dr.async_entries_for_config_entry(
            device_registry, entry.entry_id
        ):
            for kind, key in device_entry.identifiers:
                if kind == DOMAIN and key in known_devices:
                    break
            else:
                device_registry.async_remove_device(device_entry.id)

    hyperhdr_client.set_callbacks(
        {
            f"{hyperhdr_const.KEY_INSTANCE}-{hyperhdr_const.KEY_UPDATE}": async_instances_to_clients,
        }
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    assert hyperhdr_client
    if hyperhdr_client.instances is not None:
        await async_instances_to_clients_raw(hyperhdr_client.instances)

    # Prune stale entity-registry entries left from removed features.
    _async_cleanup_stale_entities(hass, entry)

    hass.data[DOMAIN][entry.entry_id][CONF_ON_UNLOAD].append(
        entry.add_update_listener(_async_entry_updated)
    )

    return True


async def _async_entry_updated(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle entry updates."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok and config_entry.entry_id in hass.data[DOMAIN]:
        config_data = hass.data[DOMAIN].pop(config_entry.entry_id)
        for func in config_data[CONF_ON_UNLOAD]:
            func()

        # Disconnect the shared instance clients.
        await asyncio.gather(
            *(
                config_data[CONF_INSTANCE_CLIENTS][
                    instance_num
                ].async_client_disconnect()
                for instance_num in config_data[CONF_INSTANCE_CLIENTS]
            )
        )

        # Disconnect the root client.
        root_client = config_data[CONF_ROOT_CLIENT]
        await root_client.async_client_disconnect()
    return unload_ok
