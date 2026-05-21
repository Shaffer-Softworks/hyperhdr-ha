"""Button platform for HyperHDR."""

from __future__ import annotations

import functools
from typing import Any

from hyperhdr import client, const as hyperhdr_const

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    get_hyperhdr_device_id,
    get_hyperhdr_unique_id,
    listen_for_instance_updates,
)
from .const import (
    CONF_INSTANCE_CLIENTS,
    CONF_PRIORITY,
    DEFAULT_PRIORITY,
    DOMAIN,
    HYPERHDR_MANUFACTURER_NAME,
    HYPERHDR_MODEL_NAME,
    SIGNAL_ENTITY_REMOVE,
    TYPE_HYPERHDR_CLEAR_PRIORITY_BUTTON,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a HyperHDR platform from config entry."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    server_id = config_entry.unique_id
    options = config_entry.options

    @callback
    def instance_add(instance_num: int, instance_name: str, sysinfo: dict[str, Any]) -> None:
        """Add entities for a new HyperHDR instance."""
        assert server_id
        hyperhdr_client = entry_data[CONF_INSTANCE_CLIENTS][instance_num]
        async_add_entities(
            [
                HyperHDRClearPriorityButton(
                    server_id,
                    instance_num,
                    instance_name,
                    options,
                    hyperhdr_client,
                )
            ]
        )

    @callback
    def instance_remove(instance_num: int) -> None:
        """Remove entities for an old HyperHDR instance."""
        assert server_id
        async_dispatcher_send(
            hass,
            SIGNAL_ENTITY_REMOVE.format(
                get_hyperhdr_unique_id(
                    server_id, instance_num, TYPE_HYPERHDR_CLEAR_PRIORITY_BUTTON
                ),
            ),
        )

    listen_for_instance_updates(hass, config_entry, instance_add, instance_remove)


class HyperHDRClearPriorityButton(ButtonEntity):
    """Button to clear the configured HyperHDR priority slot."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        options: dict[str, Any],
        hyperhdr_client: client.HyperHDRClient,
    ) -> None:
        """Initialize the button."""
        self._attr_unique_id = get_hyperhdr_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_CLEAR_PRIORITY_BUTTON
        )
        self._attr_translation_key = "clear_priority"
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._instance_name = instance_name
        self._options = options
        self._client = hyperhdr_client
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=HYPERHDR_MANUFACTURER_NAME,
            model=HYPERHDR_MODEL_NAME,
            name=self._instance_name,
            configuration_url=self._client.remote_url,
        )

    @property
    def available(self) -> bool:
        """Return server availability."""
        return bool(self._client.has_loaded_state)

    def _get_priority(self) -> int:
        """Return the configured priority level."""
        return int(self._options.get(CONF_PRIORITY, DEFAULT_PRIORITY))

    async def async_press(self) -> None:
        """Clear the configured HyperHDR priority."""
        await self._client.async_send_clear(
            **{hyperhdr_const.KEY_PRIORITY: self._get_priority()}
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ENTITY_REMOVE.format(self._attr_unique_id),
                functools.partial(self.async_remove, force_remove=True),
            )
        )
