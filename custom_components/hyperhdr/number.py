"""Number platform for HyperHDR."""

from __future__ import annotations

import functools
from typing import Any

from hyperhdr import client, const as hyperhdr_const

from homeassistant.components.number import NumberEntity, NumberEntityDescription
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
    TYPE_HYPERHDR_NUMBER_BASE,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_TIME,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_DECAY,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_UPDATE_FREQ,
    TYPE_HYPERHDR_NUMBER_HDR_TONE_MAPPING,
)

NUMBER_ENTITIES = [
    TYPE_HYPERHDR_NUMBER_SMOOTHING_TIME,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_DECAY,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_UPDATE_FREQ,
    TYPE_HYPERHDR_NUMBER_HDR_TONE_MAPPING,
]

SMOOTHING_TIME_DESCRIPTION = NumberEntityDescription(
    key="smoothing_time",
    translation_key="smoothing_time",
    icon="mdi:clock-outline",
    native_min_value=0,
    native_max_value=1000,
    native_step=1,
    native_unit_of_measurement="ms",
)

SMOOTHING_DECAY_DESCRIPTION = NumberEntityDescription(
    key="smoothing_decay",
    translation_key="smoothing_decay",
    icon="mdi:curve",
    native_min_value=0.0,
    native_max_value=1.0,
    native_step=0.01,
)

SMOOTHING_UPDATE_FREQ_DESCRIPTION = NumberEntityDescription(
    key="smoothing_update_freq",
    translation_key="smoothing_update_freq",
    icon="mdi:speedometer",
    native_min_value=0,
    native_max_value=1000,
    native_step=1,
    native_unit_of_measurement="Hz",
)

HDR_TONE_MAPPING_DESCRIPTION = NumberEntityDescription(
    key="hdr_tone_mapping",
    translation_key="hdr_tone_mapping",
    icon="mdi:palette",
    native_min_value=0.0,
    native_max_value=2.0,
    native_step=0.1,
)


def _number_unique_id(server_id: str, instance_num: int, suffix: str) -> str:
    """Calculate a number entity's unique_id."""
    return get_hyperhdr_unique_id(
        server_id,
        instance_num,
        f"{TYPE_HYPERHDR_NUMBER_BASE}_{suffix}",
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
    def instance_add(instance_num: int, instance_name: str, sysinfo: dict[str, Any]) -> None:
        """Add entities for a new HyperHDR instance."""
        assert server_id
        hyperhdr_client = entry_data[CONF_INSTANCE_CLIENTS][instance_num]

        entities: list[HyperHDRNumber] = []

        # Only create smoothing entities if the server exposes smoothing data.
        if hyperhdr_client.smoothing is not None:
            entities.extend(
                [
                    HyperHDRSmoothingTimeNumber(
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        SMOOTHING_TIME_DESCRIPTION,
                    ),
                    HyperHDRSmoothingDecayNumber(
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        SMOOTHING_DECAY_DESCRIPTION,
                    ),
                    HyperHDRSmoothingUpdateFreqNumber(
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        SMOOTHING_UPDATE_FREQ_DESCRIPTION,
                    ),
                ]
            )

        # HDR tone mapping is always available.
        entities.append(
            HyperHDRHDRToneMappingNumber(
                server_id,
                instance_num,
                instance_name,
                hyperhdr_client,
                HDR_TONE_MAPPING_DESCRIPTION,
            ),
        )

        async_add_entities(entities)

    @callback
    def instance_remove(instance_num: int) -> None:
        """Remove entities for an old HyperHDR instance."""
        assert server_id

        for number_type in NUMBER_ENTITIES:
            async_dispatcher_send(
                hass,
                SIGNAL_ENTITY_REMOVE.format(
                    _number_unique_id(server_id, instance_num, number_type),
                ),
            )

    listen_for_instance_updates(hass, config_entry, instance_add, instance_remove)


class HyperHDRNumber(NumberEntity):
    """Base class for HyperHDR number entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: NumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        self.entity_description = entity_description
        self._client = hyperhdr_client
        self._attr_native_value = None
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


class _HyperHDRSmoothingNumber(HyperHDRNumber):
    """Base class for smoothing number entities.

    The HyperHDR smoothing API is not available on all server versions.
    If ``self._client.smoothing`` is None the entity reports unavailable.
    """

    _smoothing_key: str  # Override in subclasses.

    @property
    def available(self) -> bool:
        """Return availability — requires smoothing data from the server."""
        return bool(self._client.has_loaded_state and self._client.smoothing)

    async def async_added_to_hass(self) -> None:
        """Register callbacks and populate initial state."""
        await super().async_added_to_hass()
        self._update_value()

    @callback
    def _update_value(self, _: dict[str, Any] | None = None) -> None:
        """Update the value from the client's smoothing data."""
        if self._client.smoothing:
            self._attr_native_value = self._client.smoothing.get(
                self._smoothing_key
            )
        self.async_write_ha_state()


class HyperHDRSmoothingTimeNumber(_HyperHDRSmoothingNumber):
    """Number entity for smoothing time."""

    _smoothing_key = hyperhdr_const.KEY_SMOOTHING_TIME

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: NumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(
            server_id, instance_num, instance_name, hyperhdr_client, entity_description
        )
        self._attr_unique_id = _number_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_NUMBER_SMOOTHING_TIME
        )
        self._client_callbacks = {
            f"{hyperhdr_const.KEY_SMOOTHING}-{hyperhdr_const.KEY_UPDATE}": self._update_value
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set smoothing time value."""
        await self._client.async_set_smoothing(time=int(value))


class HyperHDRSmoothingDecayNumber(_HyperHDRSmoothingNumber):
    """Number entity for smoothing decay."""

    _smoothing_key = hyperhdr_const.KEY_SMOOTHING_DECAY

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: NumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(
            server_id, instance_num, instance_name, hyperhdr_client, entity_description
        )
        self._attr_unique_id = _number_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_NUMBER_SMOOTHING_DECAY
        )
        self._client_callbacks = {
            f"{hyperhdr_const.KEY_SMOOTHING}-{hyperhdr_const.KEY_UPDATE}": self._update_value
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set smoothing decay value."""
        await self._client.async_set_smoothing(decay=value)


class HyperHDRSmoothingUpdateFreqNumber(_HyperHDRSmoothingNumber):
    """Number entity for smoothing update frequency."""

    _smoothing_key = hyperhdr_const.KEY_SMOOTHING_UPDATE_FREQUENCY

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: NumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(
            server_id, instance_num, instance_name, hyperhdr_client, entity_description
        )
        self._attr_unique_id = _number_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_NUMBER_SMOOTHING_UPDATE_FREQ
        )
        self._client_callbacks = {
            f"{hyperhdr_const.KEY_SMOOTHING}-{hyperhdr_const.KEY_UPDATE}": self._update_value
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set smoothing update frequency value."""
        await self._client.async_set_smoothing(updateFrequency=int(value))


class HyperHDRHDRToneMappingNumber(HyperHDRNumber):
    """Number entity for HDR tone mapping."""

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: NumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(
            server_id, instance_num, instance_name, hyperhdr_client, entity_description
        )
        self._attr_unique_id = _number_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_NUMBER_HDR_TONE_MAPPING
        )
        # Subscribe to both the legacy hdrToneMappingMode and the new videomodehdr
        # update events so the entity stays in sync regardless of HyperHDR version.
        self._client_callbacks: dict[str, Any] = {
            f"{hyperhdr_const.KEY_HDR_TONE_MAPPING}-{hyperhdr_const.KEY_UPDATE}": self._update_value,
        }
        _key_videomode_hdr = getattr(hyperhdr_const, "KEY_VIDEOMODE_HDR", None)
        if _key_videomode_hdr:
            self._client_callbacks[
                f"{_key_videomode_hdr}-{hyperhdr_const.KEY_UPDATE}"
            ] = self._update_value

    async def async_added_to_hass(self) -> None:
        """Register callbacks and populate initial state."""
        await super().async_added_to_hass()
        self._update_value()

    @callback
    def _update_value(self, _: dict[str, Any] | None = None) -> None:
        """Update HDR tone mapping value."""
        if hasattr(self._client, "hdr_mode"):
            self._attr_native_value = self._client.hdr_mode
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set HDR tone mapping value.

        Uses the new videomodehdr/HDR command path when available, falling back
        to the legacy hdrToneMappingMode parameter.
        """
        if hasattr(hyperhdr_const, "KEY_HDR"):
            await self._client.async_set_hdr_tone_mapping(
                **{hyperhdr_const.KEY_HDR: int(value)}
            )
        else:
            await self._client.async_set_hdr_tone_mapping(
                **{hyperhdr_const.KEY_HDR_TONE_MAPPING_MODE: int(value)}
            )
