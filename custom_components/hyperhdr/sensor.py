"""Sensor platform for HyperHDR."""

from __future__ import annotations

import functools
import logging
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
    SIGNAL_AVERAGE_COLOR,
    SIGNAL_ENTITY_REMOVE,
    TYPE_HYPERHDR_SENSOR_BASE,
    TYPE_HYPERHDR_SENSOR_VISIBLE_PRIORITY,
    TYPE_HYPERHDR_SENSOR_AVERAGE_COLOR,
)

_LOGGER = logging.getLogger(__name__)
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

    async def async_added_to_hass(self) -> None:
        """Register callbacks and populate initial state."""
        await super().async_added_to_hass()
        # The initial priorities-update fires during serverinfo loading,
        # before entity callbacks are registered.  Read the current state
        # now so the sensor doesn't stay "unknown" until the next change.
        self._update_priorities()

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
    """Class that exposes the average color for a HyperHDR instance.

    Data sources (in priority order):
    1. LED gradient stream — real-time average computed from raw LED data
       dispatched by HyperHDRLedGradientCamera (requires the gradient camera
       entity to be enabled).
    2. ``async_get_average_color()`` — server-side calculation available on
       HyperHDR v20+.
    3. Visible priority COLOR component — extracted from the priorities list
       when a static color is the active source.
    """

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

        self._device_id = get_hyperhdr_device_id(server_id, instance_num)

        # Always subscribe to priorities-update so the callback fires whenever
        # the active source changes.  The old code tried to subscribe to
        # "calculate-colors-update" which is a one-shot command response, not a
        # push subscription, so it never triggered.
        self._client_callbacks = {
            f"{KEY_PRIORITIES}-{KEY_UPDATE}": self._update_from_priorities,
        }

        # Track whether the server supports calculate-colors (v20+).
        self._server_supports_calc: bool | None = None

    async def async_added_to_hass(self) -> None:
        """Register callbacks and populate initial state."""
        await super().async_added_to_hass()

        # Listen for real-time average color updates from the LED gradient
        # camera stream.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_AVERAGE_COLOR.format(self._device_id),
                self._update_from_stream,
            )
        )

        # Populate initial state from already-loaded priorities (the initial
        # priorities-update fires before callbacks are registered).
        self._update_from_priorities()

    @callback
    def _update_from_stream(self, avg_rgb: list[int]) -> None:
        """Handle average color dispatched from the LED gradient stream."""
        if not avg_rgb or len(avg_rgb) < 3:
            return

        r, g, b = avg_rgb[0], avg_rgb[1], avg_rgb[2]
        hex_value = "#%02x%02x%02x" % (r, g, b)

        # Skip state write if the value hasn't changed.
        if hex_value == self._attr_native_value:
            return

        self._attr_native_value = hex_value
        self._attr_extra_state_attributes = {
            "rgb": [r, g, b],
            "hex": hex_value,
            "source": "led_stream",
        }
        self.async_write_ha_state()

    @callback
    def _update_from_priorities(self, _: dict[str, Any] | None = None) -> None:
        """Handle a priorities-update callback.

        If the gradient stream is providing real-time data it will overwrite
        whatever we set here on the next frame, so this mainly covers the case
        where the gradient camera is disabled or the LED stream is not running.
        """
        # Schedule the async helper so we can try async_get_average_color.
        self.hass.async_create_task(self._async_update_average())

    async def _async_update_average(self) -> None:
        """Attempt to determine the average color from available sources."""
        avg_value: list[int] | None = None
        attrs: dict[str, Any] = {}
        source = "unknown"

        # 1) Try the server-side calculate-colors command (v20+).
        if self._server_supports_calc is not False and hasattr(
            self._client, "async_get_average_color"
        ):
            try:
                resp = await self._client.async_get_average_color()
                if resp and isinstance(resp, dict) and resp.get("success"):
                    info = resp.get("info", {})
                    rgb = info.get("rgb") or info.get(KEY_RGB)
                    if isinstance(rgb, (list, tuple)) and len(rgb) >= 3:
                        avg_value = [int(rgb[0]), int(rgb[1]), int(rgb[2])]
                        attrs.update(info)
                        source = "calculate-colors"
                        self._server_supports_calc = True
                    else:
                        self._server_supports_calc = False
                else:
                    self._server_supports_calc = False
            except Exception:  # pylint: disable=broad-except
                _LOGGER.debug(
                    "async_get_average_color not supported on this server"
                )
                self._server_supports_calc = False

        # 2) Fall back to visible priorities with a COLOR component.
        if avg_value is None:
            for priority in self._client.priorities or []:
                if not (KEY_VISIBLE in priority and priority[KEY_VISIBLE] is True):
                    continue

                attrs = {
                    "component_id": priority[KEY_COMPONENTID],
                    "origin": priority.get(KEY_ORIGIN),
                    "priority": priority.get(KEY_PRIORITY),
                    "owner": priority.get(KEY_OWNER),
                }

                if priority[KEY_COMPONENTID] == "COLOR":
                    avg_value = priority.get(KEY_VALUE, {}).get(KEY_RGB)
                    attrs["color"] = priority.get(KEY_VALUE)
                    source = "priority_color"
                else:
                    source = "priority_component"
                break

        # Build hex representation if we have RGB data.
        hex_value = None
        if avg_value and isinstance(avg_value, (list, tuple)) and len(avg_value) >= 3:
            r, g, b = int(avg_value[0]), int(avg_value[1]), int(avg_value[2])
            hex_value = "#%02x%02x%02x" % (r, g, b)
            attrs.setdefault("rgb", [r, g, b])
            attrs["hex"] = hex_value

        attrs["source"] = source
        self._attr_native_value = hex_value if hex_value else None
        self._attr_extra_state_attributes = attrs
        self.async_write_ha_state()
