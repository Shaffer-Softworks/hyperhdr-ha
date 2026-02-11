"""Select platform for HyperHDR."""

from __future__ import annotations

import functools
from typing import Any

from hyperhdr import client, const as hyperhdr_const

from homeassistant.components.select import SelectEntity, SelectEntityDescription
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
    DOMAIN,
    HYPERHDR_MANUFACTURER_NAME,
    HYPERHDR_MODEL_NAME,
    SIGNAL_ENTITY_REMOVE,
    TYPE_HYPERHDR_SELECT_BASE,
    TYPE_HYPERHDR_SELECT_SMOOTHING_TYPE,
)

SELECT_ENTITIES = [
    TYPE_HYPERHDR_SELECT_SMOOTHING_TYPE,
]

SMOOTHING_TYPE_OPTIONS = [
    hyperhdr_const.SMOOTHING_TYPE_LINEAR,
    hyperhdr_const.SMOOTHING_TYPE_EXPONENTIAL,
    hyperhdr_const.SMOOTHING_TYPE_INERTIA,
    hyperhdr_const.SMOOTHING_TYPE_HYBRID_RGB,
    hyperhdr_const.SMOOTHING_TYPE_YUV,
]

SMOOTHING_TYPE_DESCRIPTION = SelectEntityDescription(
    key="smoothing_type",
    translation_key="smoothing_type",
    icon="mdi:sine-wave",
)


def _select_unique_id(server_id: str, instance_num: int, suffix: str) -> str:
    """Calculate a select entity's unique_id."""
    return get_hyperhdr_unique_id(
        server_id,
        instance_num,
        f"{TYPE_HYPERHDR_SELECT_BASE}_{suffix}",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a HyperHDR platform from config entry."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    server_id = config_entry.unique_id

    @callback
    def instance_add(instance_num: int, instance_name: str) -> None:
        """Add entities for a new HyperHDR instance."""
        assert server_id
        hyperhdr_client = entry_data[CONF_INSTANCE_CLIENTS][instance_num]

        # Only create smoothing entities if the server exposes smoothing data.
        if hyperhdr_client.smoothing is None:
            return

        async_add_entities(
            [
                HyperHDRSmoothingTypeSelect(
                    server_id,
                    instance_num,
                    instance_name,
                    hyperhdr_client,
                    SMOOTHING_TYPE_DESCRIPTION,
                ),
            ]
        )

    @callback
    def instance_remove(instance_num: int) -> None:
        """Remove entities for an old HyperHDR instance."""
        assert server_id

        for select_type in SELECT_ENTITIES:
            async_dispatcher_send(
                hass,
                SIGNAL_ENTITY_REMOVE.format(
                    _select_unique_id(server_id, instance_num, select_type),
                ),
            )

    listen_for_instance_updates(hass, config_entry, instance_add, instance_remove)


class HyperHDRSelect(SelectEntity):
    """Base class for HyperHDR select entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: SelectEntityDescription,
    ) -> None:
        """Initialize the select."""
        self.entity_description = entity_description
        self._client = hyperhdr_client
        self._attr_current_option = None
        self._client_callbacks: dict[str, Any] = {}

        device_id = get_hyperhdr_device_id(server_id, instance_num)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=HYPERHDR_MANUFACTURER_NAME,
            model=HYPERHDR_MODEL_NAME,
            name=instance_name,
            configuration_url=self._client.remote_url,
        )

    @property
    def available(self) -> bool:
        """Return server availability."""
        return bool(self._client.has_loaded_state)

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ENTITY_REMOVE.format(self._attr_unique_id),
                functools.partial(self.async_remove, force_remove=True),
            )
        )

        self._client.add_callbacks(self._client_callbacks)

    async def async_will_remove_from_hass(self) -> None:
        """Cleanup prior to hass removal."""
        self._client.remove_callbacks(self._client_callbacks)


class HyperHDRSmoothingTypeSelect(HyperHDRSelect):
    """Select entity for smoothing type.

    The HyperHDR smoothing API is not available on all server versions.
    If ``self._client.smoothing`` is None the entity reports unavailable.
    """

    _attr_options = SMOOTHING_TYPE_OPTIONS

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: SelectEntityDescription,
    ) -> None:
        """Initialize the select."""
        super().__init__(
            server_id, instance_num, instance_name, hyperhdr_client, entity_description
        )
        self._attr_unique_id = _select_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_SELECT_SMOOTHING_TYPE
        )
        self._client_callbacks = {
            f"{hyperhdr_const.KEY_SMOOTHING}-{hyperhdr_const.KEY_UPDATE}": self._update_smoothing_type
        }

    @property
    def available(self) -> bool:
        """Return availability — requires smoothing data from the server."""
        return bool(self._client.has_loaded_state and self._client.smoothing)

    async def async_added_to_hass(self) -> None:
        """Register callbacks and populate initial state."""
        await super().async_added_to_hass()
        self._update_smoothing_type()

    @callback
    def _update_smoothing_type(self, _: dict[str, Any] | None = None) -> None:
        """Update smoothing type selection."""
        if self._client.smoothing:
            self._attr_current_option = self._client.smoothing.get(
                hyperhdr_const.KEY_SMOOTHING_TYPE
            )
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Set smoothing type."""
        await self._client.async_set_smoothing(smoothingType=option)
