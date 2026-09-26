"""Switch platform for HyperHDR."""

from __future__ import annotations

import functools
from typing import Any

from hyperhdr import client
from hyperhdr.const import (
    KEY_COMPONENT,
    KEY_COMPONENTID_ALL,
    KEY_COMPONENTID_BLACKBORDER,
    KEY_COMPONENTID_BOBLIGHTSERVER,
    KEY_COMPONENTID_FORWARDER,
    KEY_COMPONENTID_SYSTEMGRABBER,
    KEY_COMPONENTID_LEDDEVICE,
    KEY_COMPONENTID_SMOOTHING,
    KEY_COMPONENTID_HDR,
    KEY_COMPONENTID_TO_NAME,
    KEY_COMPONENTID_VIDEOGRABBER,
    KEY_COMPONENTS,
    KEY_COMPONENTSTATE,
    KEY_ENABLED,
    KEY_NAME,
    KEY_SMOOTHING_ANTI_FLICKERING_FILTER,
    KEY_SMOOTHING_CONTINUOUS_OUTPUT,
    KEY_STATE,
    KEY_UPDATE,
)

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

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
    TYPE_HYPERHDR_COMPONENT_SWITCH_BASE,
    TYPE_HYPERHDR_SWITCH_ANTI_FLICKER,
    TYPE_HYPERHDR_SWITCH_CONTINUOUS_OUTPUT,
)
from .smoothing_config import async_patch_smoothing_config, smoothing_config_available

COMPONENT_SWITCHES = [
    KEY_COMPONENTID_ALL,
    KEY_COMPONENTID_SMOOTHING,
    KEY_COMPONENTID_BLACKBORDER,
    KEY_COMPONENTID_FORWARDER,
    KEY_COMPONENTID_BOBLIGHTSERVER,
    KEY_COMPONENTID_SYSTEMGRABBER,
    KEY_COMPONENTID_LEDDEVICE,
    KEY_COMPONENTID_VIDEOGRABBER,
    KEY_COMPONENTID_HDR,
]


def _component_to_unique_id(server_id: str, component: str, instance_num: int) -> str:
    """Convert a component to a unique_id."""
    return get_hyperhdr_unique_id(
        server_id,
        instance_num,
        slugify(
            f"{TYPE_HYPERHDR_COMPONENT_SWITCH_BASE} {KEY_COMPONENTID_TO_NAME[component]}"
        ),
    )


def _component_to_translation_key(component: str) -> str:
    return {
        KEY_COMPONENTID_ALL: "all",
        KEY_COMPONENTID_SMOOTHING: "smoothing",
        KEY_COMPONENTID_BLACKBORDER: "blackbar_detection",
        KEY_COMPONENTID_FORWARDER: "forwarder",
        KEY_COMPONENTID_BOBLIGHTSERVER: "boblight_server",
        KEY_COMPONENTID_SYSTEMGRABBER: "platform_capture",
        KEY_COMPONENTID_LEDDEVICE: "led_device",
        KEY_COMPONENTID_VIDEOGRABBER: "usb_capture",
        KEY_COMPONENTID_HDR: "hdr_tone_mapping",
    }[component]


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
        available_components = {
            component.get(KEY_NAME)
            for component in (hyperhdr_client.components or [])
            if isinstance(component, dict)
        }
        components_to_add = [
            component
            for component in COMPONENT_SWITCHES
            if not available_components or component in available_components
        ]
        async_add_entities(
            [
                HyperHDRComponentSwitch(
                    server_id,
                    instance_num,
                    instance_name,
                    component,
                    hyperhdr_client,
                )
                for component in components_to_add
            ]
            + (
                [
                    HyperHDRSmoothingConfigSwitch(
                        config_entry.entry_id,
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        TYPE_HYPERHDR_SWITCH_ANTI_FLICKER,
                        "smoothing_anti_flicker",
                        KEY_SMOOTHING_ANTI_FLICKERING_FILTER,
                    ),
                    HyperHDRSmoothingConfigSwitch(
                        config_entry.entry_id,
                        server_id,
                        instance_num,
                        instance_name,
                        hyperhdr_client,
                        TYPE_HYPERHDR_SWITCH_CONTINUOUS_OUTPUT,
                        "smoothing_continuous_output",
                        KEY_SMOOTHING_CONTINUOUS_OUTPUT,
                    ),
                ]
                if smoothing_config_available(entry_data, instance_num)
                else []
            )
        )

    @callback
    def instance_remove(instance_num: int) -> None:
        """Remove entities for an old HyperHDR instance."""
        assert server_id
        for component in COMPONENT_SWITCHES:
            async_dispatcher_send(
                hass,
                SIGNAL_ENTITY_REMOVE.format(
                    _component_to_unique_id(server_id, component, instance_num),
                ),
            )
        for switch_type in (
            TYPE_HYPERHDR_SWITCH_ANTI_FLICKER,
            TYPE_HYPERHDR_SWITCH_CONTINUOUS_OUTPUT,
        ):
            async_dispatcher_send(
                hass,
                SIGNAL_ENTITY_REMOVE.format(
                    get_hyperhdr_unique_id(server_id, instance_num, switch_type),
                ),
            )

    listen_for_instance_updates(hass, config_entry, instance_add, instance_remove)


class HyperHDRComponentSwitch(SwitchEntity):
    """ComponentBinarySwitch switch class."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False
    _attr_has_entity_name = True
    # These component controls are for advanced users and are disabled by default.
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        component_name: str,
        hyperhdr_client: client.HyperHDRClient,
    ) -> None:
        """Initialize the switch."""
        self._attr_unique_id = _component_to_unique_id(
            server_id, component_name, instance_num
        )
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._attr_translation_key = _component_to_translation_key(component_name)
        self._instance_name = instance_name
        self._component_name = component_name
        self._client = hyperhdr_client
        self._client_callbacks = {
            f"{KEY_COMPONENTS}-{KEY_UPDATE}": self._update_components
        }
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=HYPERHDR_MANUFACTURER_NAME,
            model=HYPERHDR_MODEL_NAME,
            name=self._instance_name,
            configuration_url=self._client.remote_url,
        )

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        for component in self._client.components or []:
            if component[KEY_NAME] == self._component_name:
                return bool(component.setdefault(KEY_ENABLED, False))
        return False

    @property
    def available(self) -> bool:
        """Return server availability."""
        return bool(self._client.has_loaded_state)

    async def _async_send_set_component(self, value: bool) -> None:
        """Send a component control request."""
        if (
            self._client.components is not None
            and self._component_name
            not in {c.get(KEY_NAME) for c in (self._client.components or []) if isinstance(c, dict)}
        ):
            return
        await self._client.async_send_set_component(
            **{
                KEY_COMPONENTSTATE: {
                    KEY_COMPONENT: self._component_name,
                    KEY_STATE: value,
                }
            }
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self._async_send_set_component(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self._async_send_set_component(False)

    @callback
    def _update_components(self, _: dict[str, Any] | None = None) -> None:
        """Update HyperHDR components."""
        self.async_write_ha_state()

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

        # Populate initial state from already-loaded client data.
        self._update_components()

    async def async_will_remove_from_hass(self) -> None:
        """Cleanup prior to hass removal."""
        self._client.remove_callbacks(self._client_callbacks)


class HyperHDRSmoothingConfigSwitch(SwitchEntity):
    """Switch backed by HyperHDR v22 smoothing config fields."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        entry_id: str,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
        type_suffix: str,
        translation_key: str,
        config_key: str,
    ) -> None:
        """Initialize the switch."""
        self._entry_id = entry_id
        self._server_id = server_id
        self._instance_num = instance_num
        self._config_key = config_key
        self._client = hyperhdr_client
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._attr_unique_id = get_hyperhdr_unique_id(
            server_id, instance_num, type_suffix
        )
        self._attr_translation_key = translation_key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=HYPERHDR_MANUFACTURER_NAME,
            model=HYPERHDR_MODEL_NAME,
            name=instance_name,
            configuration_url=self._client.remote_url,
        )

    @property
    def available(self) -> bool:
        """Return availability — requires smoothing config."""
        return bool(self._client.has_loaded_state and self._client.smoothing)

    @property
    def is_on(self) -> bool:
        """Return true if the config flag is enabled."""
        if not self._client.smoothing:
            return False
        return bool(self._client.smoothing.get(self._config_key, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the smoothing config flag."""
        await async_patch_smoothing_config(
            self.hass,
            self._entry_id,
            self._server_id,
            self._instance_num,
            **{self._config_key: True},
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the smoothing config flag."""
        await async_patch_smoothing_config(
            self.hass,
            self._entry_id,
            self._server_id,
            self._instance_num,
            **{self._config_key: False},
        )

    @callback
    def _update_state(self, _: dict[str, Any] | None = None) -> None:
        """Refresh switch state from cached smoothing config."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register remove and smoothing-config listeners."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ENTITY_REMOVE.format(self._attr_unique_id),
                functools.partial(self.async_remove, force_remove=True),
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SMOOTHING_CONFIG.format(self._device_id),
                self._update_state,
            )
        )
        self._update_state()
