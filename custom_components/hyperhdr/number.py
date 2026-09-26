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
    SIGNAL_SMOOTHING_CONFIG,
    TYPE_HYPERHDR_NUMBER_BASE,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_DAMPING,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_FACTOR,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_STIFFNESS,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_TIME,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_UPDATE_FREQ,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_Y_LIMIT,
)
from .smoothing_config import async_patch_smoothing_config, smoothing_config_available

NUMBER_ENTITIES = [
    TYPE_HYPERHDR_NUMBER_SMOOTHING_TIME,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_UPDATE_FREQ,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_FACTOR,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_STIFFNESS,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_DAMPING,
    TYPE_HYPERHDR_NUMBER_SMOOTHING_Y_LIMIT,
]

SMOOTHING_TIME_DESCRIPTION = NumberEntityDescription(
    key="smoothing_time",
    translation_key="smoothing_time",
    icon="mdi:clock-outline",
    native_min_value=25,
    native_max_value=5000,
    native_step=25,
    native_unit_of_measurement="ms",
)

SMOOTHING_UPDATE_FREQ_DESCRIPTION = NumberEntityDescription(
    key="smoothing_update_freq",
    translation_key="smoothing_update_freq",
    icon="mdi:speedometer",
    native_min_value=20,
    native_max_value=200,
    native_step=5,
    native_unit_of_measurement="Hz",
)

SMOOTHING_FACTOR_DESCRIPTION = NumberEntityDescription(
    key="smoothing_factor",
    translation_key="smoothing_factor",
    icon="mdi:chart-bell-curve",
    native_min_value=0.0,
    native_max_value=1.0,
    native_step=0.05,
)

SMOOTHING_STIFFNESS_DESCRIPTION = NumberEntityDescription(
    key="smoothing_stiffness",
    translation_key="smoothing_stiffness",
    icon="mdi:spring",
    native_min_value=0,
    native_max_value=1000,
    native_step=10,
)

SMOOTHING_DAMPING_DESCRIPTION = NumberEntityDescription(
    key="smoothing_damping",
    translation_key="smoothing_damping",
    icon="mdi:waves",
    native_min_value=0,
    native_max_value=1000,
    native_step=2,
)

SMOOTHING_Y_LIMIT_DESCRIPTION = NumberEntityDescription(
    key="smoothing_y_limit",
    translation_key="smoothing_y_limit",
    icon="mdi:arrow-collapse-vertical",
    native_min_value=0.0,
    native_max_value=1.0,
    native_step=0.01,
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

        if smoothing_config_available(entry_data, instance_num):
            entities.extend(
                [
                    HyperHDRSmoothingConfigNumber(
                        config_entry.entry_id,
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        SMOOTHING_TIME_DESCRIPTION,
                        TYPE_HYPERHDR_NUMBER_SMOOTHING_TIME,
                        hyperhdr_const.KEY_SMOOTHING_TIME_MS,
                        cast_int=True,
                    ),
                    HyperHDRSmoothingConfigNumber(
                        config_entry.entry_id,
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        SMOOTHING_UPDATE_FREQ_DESCRIPTION,
                        TYPE_HYPERHDR_NUMBER_SMOOTHING_UPDATE_FREQ,
                        hyperhdr_const.KEY_SMOOTHING_UPDATE_FREQUENCY,
                        cast_int=True,
                    ),
                    HyperHDRSmoothingConfigNumber(
                        config_entry.entry_id,
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        SMOOTHING_FACTOR_DESCRIPTION,
                        TYPE_HYPERHDR_NUMBER_SMOOTHING_FACTOR,
                        hyperhdr_const.KEY_SMOOTHING_FACTOR,
                    ),
                    HyperHDRSmoothingConfigNumber(
                        config_entry.entry_id,
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        SMOOTHING_STIFFNESS_DESCRIPTION,
                        TYPE_HYPERHDR_NUMBER_SMOOTHING_STIFFNESS,
                        hyperhdr_const.KEY_SMOOTHING_STIFFNESS,
                        cast_int=True,
                    ),
                    HyperHDRSmoothingConfigNumber(
                        config_entry.entry_id,
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        SMOOTHING_DAMPING_DESCRIPTION,
                        TYPE_HYPERHDR_NUMBER_SMOOTHING_DAMPING,
                        hyperhdr_const.KEY_SMOOTHING_DAMPING,
                        cast_int=True,
                    ),
                    HyperHDRSmoothingConfigNumber(
                        config_entry.entry_id,
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        SMOOTHING_Y_LIMIT_DESCRIPTION,
                        TYPE_HYPERHDR_NUMBER_SMOOTHING_Y_LIMIT,
                        hyperhdr_const.KEY_SMOOTHING_Y_LIMIT,
                    ),
                ]
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


class HyperHDRSmoothingConfigNumber(HyperHDRNumber):
    """Number entity backed by HyperHDR v22 smoothing config."""

    def __init__(
        self,
        entry_id: str,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: NumberEntityDescription,
        type_suffix: str,
        config_key: str,
        *,
        cast_int: bool = False,
    ) -> None:
        """Initialize the number."""
        super().__init__(
            server_id, instance_num, instance_name, hyperhdr_client, entity_description
        )
        self._entry_id = entry_id
        self._server_id = server_id
        self._instance_num = instance_num
        self._config_key = config_key
        self._cast_int = cast_int
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._attr_unique_id = _number_unique_id(server_id, instance_num, type_suffix)

    @property
    def available(self) -> bool:
        """Return availability — requires cached smoothing config."""
        return bool(self._client.has_loaded_state and self._client.smoothing)

    async def async_added_to_hass(self) -> None:
        """Register callbacks and populate initial state."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SMOOTHING_CONFIG.format(self._device_id),
                self._update_value,
            )
        )
        self._update_value()

    @callback
    def _update_value(self, _: dict[str, Any] | None = None) -> None:
        """Update the value from the client's smoothing config cache."""
        if self._client.smoothing:
            value = self._client.smoothing.get(self._config_key)
            if value is not None:
                self._attr_native_value = float(value)
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set smoothing config field."""
        field_value: float | int = int(value) if self._cast_int else value
        await async_patch_smoothing_config(
            self.hass,
            self._entry_id,
            self._server_id,
            self._instance_num,
            **{self._config_key: field_value},
        )
