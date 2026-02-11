"""Sensor platform for HyperHDR."""

from __future__ import annotations

import functools
from typing import Any

from hyperhdr import client
from hyperhdr import const as hyperhdr_const
from hyperhdr.const import (
    KEY_COMPONENTID,
    KEY_ORIGIN,
    KEY_OWNER,
    KEY_PRIORITIES,
    KEY_PRIORITY,
    KEY_RGB,
    KEY_UPDATE,
    KEY_VALUE,
    KEY_VISIBLE,
)

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
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
    TYPE_HYPERHDR_SENSOR_BASE,
    TYPE_HYPERHDR_SENSOR_VISIBLE_PRIORITY,
    TYPE_HYPERHDR_SENSOR_AVERAGE_COLOR,
)
SENSORS = [TYPE_HYPERHDR_SENSOR_VISIBLE_PRIORITY, TYPE_HYPERHDR_SENSOR_AVERAGE_COLOR]
PRIORITY_SENSOR_DESCRIPTION = SensorEntityDescription(
    key="visible_priority",
    translation_key="visible_priority",
    icon="mdi:lava-lamp",
)


def _sensor_unique_id(server_id: str, instance_num: int, suffix: str) -> str:
    """Calculate a sensor's unique_id."""
    return get_hyperhdr_unique_id(
        server_id,
        instance_num,
        f"{TYPE_HYPERHDR_SENSOR_BASE}_{suffix}",
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
        sensors = [
            HyperHDRVisiblePrioritySensor(
                server_id,
                instance_num,
                instance_name,
                entry_data[CONF_INSTANCE_CLIENTS][instance_num],
                PRIORITY_SENSOR_DESCRIPTION,
            ),
            HyperHDRAverageColorSensor(
                server_id,
                instance_num,
                instance_name,
                entry_data[CONF_INSTANCE_CLIENTS][instance_num],
            ),
        ]

        async_add_entities(sensors)

    @callback
    def instance_remove(instance_num: int) -> None:
        """Remove entities for an old HyperHDR instance."""
        assert server_id

        for sensor in SENSORS:
            async_dispatcher_send(
                hass,
                SIGNAL_ENTITY_REMOVE.format(
                    _sensor_unique_id(server_id, instance_num, sensor),
                ),
            )

    listen_for_instance_updates(hass, config_entry, instance_add, instance_remove)


class HyperHDRSensor(SensorEntity):
    """Sensor class."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
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


class HyperHDRVisiblePrioritySensor(HyperHDRSensor):
    """Class that displays the visible priority of a HyperHDR instance."""

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(
            server_id, instance_num, instance_name, hyperhdr_client, entity_description
        )

        self._attr_unique_id = _sensor_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_SENSOR_VISIBLE_PRIORITY
        )

        self._client_callbacks = {
            f"{KEY_PRIORITIES}-{KEY_UPDATE}": self._update_priorities
        }

    @callback
    def _update_priorities(self, _: dict[str, Any] | None = None) -> None:
        """Update HyperHDR priorities."""
        state_value = None
        attrs = {}

        for priority in self._client.priorities or []:
            if not (KEY_VISIBLE in priority and priority[KEY_VISIBLE] is True):
                continue

            if priority[KEY_COMPONENTID] == "COLOR":
                state_value = priority[KEY_VALUE][KEY_RGB]
            else:
                state_value = priority.get(KEY_OWNER)

            attrs = {
                "component_id": priority[KEY_COMPONENTID],
                "origin": priority[KEY_ORIGIN],
                "priority": priority[KEY_PRIORITY],
                "owner": priority.get(KEY_OWNER),
            }

            if priority[KEY_COMPONENTID] == "COLOR":
                attrs["color"] = priority[KEY_VALUE]
            else:
                attrs["color"] = None

        self._attr_native_value = state_value
        self._attr_extra_state_attributes = attrs

        self.async_write_ha_state()


AVERAGE_SENSOR_DESCRIPTION = SensorEntityDescription(
    key="average_color",
    translation_key="average_color",
    icon="mdi:palette",
    native_unit_of_measurement=None,
)


class HyperHDRAverageColorSensor(HyperHDRSensor):
    """Class that exposes the average color for a HyperHDR instance."""

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(
            server_id,
            instance_num,
            instance_name,
            hyperhdr_client,
            AVERAGE_SENSOR_DESCRIPTION,
        )

        self._attr_unique_id = _sensor_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_SENSOR_AVERAGE_COLOR
        )

        # Prefer dedicated average color updates from the client if available,
        # otherwise fall back to observing priorities and deriving a representative
        # color from visible priorities.
        client_key = getattr(hyperhdr_const, "KEY_AVERAGE_COLOR", None)
        if client_key:
            self._client_callbacks = {f"{client_key}-{KEY_UPDATE}": self._update_average}
        else:
            self._client_callbacks = {f"{KEY_PRIORITIES}-{KEY_UPDATE}": self._update_average}

    @callback
    def _update_average(self, _: dict[str, Any] | None = None) -> None:
        """Update the average color value from the client."""
        avg_value = None
        attrs: dict[str, Any] = {}

        # 1) If client exposes average_color attribute, use it.
        if hasattr(self._client, "average_color") and self._client.average_color:
            avg = self._client.average_color
            # Could be a dict with 'rgb' or a simple list
            if isinstance(avg, dict):
                avg_value = avg.get(KEY_RGB) or avg.get("rgb")
                attrs.update(avg)
            else:
                avg_value = avg

        # 2) If hyperhdr.const defines a KEY_AVERAGE payload and the client
        # populates it, prefer that structure (handled by callback wiring).
        if avg_value is None:
            # Fall back to visible priorities: prefer COLOR component values.
            for priority in self._client.priorities or []:
                if not (KEY_VISIBLE in priority and priority[KEY_VISIBLE] is True):
                    continue
                if priority[KEY_COMPONENTID] == "COLOR":
                    avg_value = priority[KEY_VALUE].get(KEY_RGB)
                    attrs = {
                        "component_id": priority[KEY_COMPONENTID],
                        "origin": priority.get(KEY_ORIGIN),
                        "priority": priority.get(KEY_PRIORITY),
                        "owner": priority.get(KEY_OWNER),
                        "color": priority[KEY_VALUE],
                    }
                    break

        # Update entity state
        # Convert RGB list to hex string for better state display
        hex_value = None
        if avg_value and isinstance(avg_value, (list, tuple)) and len(avg_value) >= 3:
            r, g, b = avg_value[0], avg_value[1], avg_value[2]
            hex_value = "#%02x%02x%02x" % (r, g, b)
            attrs.setdefault("rgb", [r, g, b])
            attrs["hex"] = hex_value

        self._attr_native_value = hex_value or avg_value
        self._attr_extra_state_attributes = attrs
        self.async_write_ha_state()
