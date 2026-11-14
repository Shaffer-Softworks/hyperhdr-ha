"""Select platform for HyperHDR."""

from __future__ import annotations

import copy
import functools
import logging
from typing import Any

from hyperhdr import client, const as hyperhdr_const

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    CONF_ADMIN_PASSWORD,
    CONF_INSTANCE_CLIENTS,
    DOMAIN,
    HYPERHDR_MANUFACTURER_NAME,
    HYPERHDR_MODEL_NAME,
    SIGNAL_ENTITY_REMOVE,
    SIGNAL_SMOOTHING_CONFIG,
    TYPE_HYPERHDR_SELECT_BASE,
    TYPE_HYPERHDR_SELECT_HDR_TONE_MAPPING,
    TYPE_HYPERHDR_SELECT_SMOOTHING_TYPE,
)
from .smoothing_config import (
    async_ensure_config_auth,
    async_patch_smoothing_config,
    smoothing_config_available,
)

_LOGGER = logging.getLogger(__name__)

SELECT_ENTITIES = [
    TYPE_HYPERHDR_SELECT_HDR_TONE_MAPPING,
    TYPE_HYPERHDR_SELECT_SMOOTHING_TYPE,
]

HDR_MODE_OFF = "Off"
HDR_MODE_ON = "On"
HDR_MODE_AUTO = "Auto"

HDR_MODE_OPTIONS = (HDR_MODE_OFF, HDR_MODE_ON, HDR_MODE_AUTO)

KEY_AUTOMATIC_TONE_MAPPING = "automaticToneMapping"
KEY_ENABLE = "enable"

SMOOTHING_TYPE_OPTIONS = list(
    getattr(
        hyperhdr_const,
        "SMOOTHING_TYPE_OPTIONS_V22",
        (
            "Stepper",
            "YuvInterpolator",
            "RgbInterpolator",
            "HybridInterpolator",
            "HybridRgbInterpolator",
            "ExponentialInterpolator",
        ),
    )
)

HDR_TONE_MAPPING_DESCRIPTION = SelectEntityDescription(
    key="hdr_tone_mapping",
    translation_key="hdr_tone_mapping",
    icon="mdi:contrast-box",
    entity_category=EntityCategory.CONFIG,
)

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


def _normalize_videomodehdr(mode: Any) -> str | None:
    """Map HyperHDR videomodehdr (0/1/2 or bool) to Off/On/Auto labels."""
    if mode is True or mode == 1:
        return HDR_MODE_ON
    if mode is False or mode == 0:
        return HDR_MODE_OFF
    if mode == 2:
        return HDR_MODE_AUTO
    return None


def _config_info(response: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract the config ``info`` object from a getconfig response."""
    if not isinstance(response, dict) or not client.ResponseOK(response):
        return None
    info = response.get("info")
    if isinstance(info, dict):
        return info
    # Some wrappers may already be the info payload.
    if KEY_AUTOMATIC_TONE_MAPPING in response or "smoothing" in response:
        return response
    return None


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

        entities: list[SelectEntity] = [
            HyperHDRHdrToneMappingSelect(
                config_entry.entry_id,
                server_id,
                instance_num,
                instance_name,
                hyperhdr_client,
                HDR_TONE_MAPPING_DESCRIPTION,
            )
        ]

        if smoothing_config_available(entry_data, instance_num):
            entities.append(
                HyperHDRSmoothingTypeSelect(
                    config_entry.entry_id,
                    server_id,
                    instance_num,
                    instance_name,
                    hyperhdr_client,
                    SMOOTHING_TYPE_DESCRIPTION,
                )
            )

        async_add_entities(entities)

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


class HyperHDRHdrToneMappingSelect(HyperHDRSelect):
    """Select entity for HDR tone mapping mode (Off / On / Auto).

    Off/On map to HyperHDR ``videomodehdr`` (0/1). Auto maps to Image
    Processing ``automaticToneMapping.enable`` via config get/set — ``HDR: 2``
    is accepted by the schema but is coerced to On on current HyperHDR builds.
    """

    _attr_options = list(HDR_MODE_OPTIONS)
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        entry_id: str,
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
        self._entry_id = entry_id
        self._attr_unique_id = _select_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_SELECT_HDR_TONE_MAPPING
        )
        self._auto_enabled: bool | None = None
        self._auto_config: dict[str, Any] | None = None
        self._client_callbacks = {
            f"{hyperhdr_const.KEY_VIDEOMODE_HDR}-{hyperhdr_const.KEY_UPDATE}": (
                self._update_hdr_mode
            ),
            f"{hyperhdr_const.KEY_CLIENT}-{hyperhdr_const.KEY_UPDATE}": (
                self._update_hdr_mode
            ),
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks and populate initial state."""
        await super().async_added_to_hass()
        await self._async_refresh_auto_config()
        self._update_hdr_mode()

    def _admin_password(self) -> str | None:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if not entry:
            return None
        return entry.data.get(CONF_ADMIN_PASSWORD) or None

    async def _async_refresh_auto_config(self) -> None:
        """Load automaticToneMapping from HyperHDR config."""
        if not await async_ensure_config_auth(
            self._client, admin_password=self._admin_password()
        ):
            self._auto_config = None
            self._auto_enabled = None
            return
        response = await self._client.async_get_config()
        info = _config_info(response if isinstance(response, dict) else None)
        if not info:
            self._auto_config = None
            self._auto_enabled = None
            return
        atm = info.get(KEY_AUTOMATIC_TONE_MAPPING)
        if isinstance(atm, dict):
            self._auto_config = copy.deepcopy(atm)
            self._auto_enabled = bool(atm.get(KEY_ENABLE, False))
        else:
            self._auto_config = None
            self._auto_enabled = None

    async def _async_set_auto_enabled(self, enable: bool) -> bool:
        """Write automaticToneMapping.enable via config setconfig."""
        if not await async_ensure_config_auth(
            self._client, admin_password=self._admin_password()
        ):
            _LOGGER.warning(
                "Cannot change HyperHDR automatic tone mapping; config auth failed"
            )
            return False
        if self._auto_config is None:
            await self._async_refresh_auto_config()
        if self._auto_config is None:
            _LOGGER.warning(
                "Cannot change HyperHDR automatic tone mapping; config unavailable"
            )
            return False
        payload = {**self._auto_config, KEY_ENABLE: enable}
        response = await self._client.async_set_config(
            config={KEY_AUTOMATIC_TONE_MAPPING: payload}
        )
        if not client.ResponseOK(response):
            _LOGGER.warning(
                "Failed to set HyperHDR automaticToneMapping.enable=%s: %s",
                enable,
                (response or {}).get("error") if isinstance(response, dict) else None,
            )
            return False
        self._auto_config = payload
        self._auto_enabled = enable
        return True

    @callback
    def _update_hdr_mode(self, _: dict[str, Any] | None = None) -> None:
        """Update selection from videomodehdr and cached auto-enable flag."""
        if self._auto_enabled:
            self._attr_current_option = HDR_MODE_AUTO
        else:
            self._attr_current_option = (
                _normalize_videomodehdr(self._client.hdr_mode) or HDR_MODE_OFF
            )
            if self._attr_current_option == HDR_MODE_AUTO:
                # Schema value 2 without config auto — treat as On for display.
                self._attr_current_option = HDR_MODE_ON
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Set HDR tone mapping mode."""
        if option not in HDR_MODE_OPTIONS:
            return

        if option == HDR_MODE_AUTO:
            if not await self._async_set_auto_enabled(True):
                return
            self._update_hdr_mode()
            return

        # Manual Off/On: disable automatic tone mapping when enabled, then set
        # videomodehdr. Config auth failure still allows Off/On via JSON API.
        if self._auto_enabled:
            await self._async_set_auto_enabled(False)

        hdr_value = 1 if option == HDR_MODE_ON else 0
        await self._client.async_set_hdr_mode(**{hyperhdr_const.KEY_HDR: hdr_value})
        self._update_hdr_mode()


class HyperHDRSmoothingTypeSelect(HyperHDRSelect):
    """Select entity for v22 smoothing interpolator type."""

    _attr_options = SMOOTHING_TYPE_OPTIONS

    def __init__(
        self,
        entry_id: str,
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
        self._entry_id = entry_id
        self._server_id = server_id
        self._instance_num = instance_num
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._attr_unique_id = _select_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_SELECT_SMOOTHING_TYPE
        )

    @property
    def available(self) -> bool:
        """Return availability — requires smoothing config."""
        return bool(self._client.has_loaded_state and self._client.smoothing)

    async def async_added_to_hass(self) -> None:
        """Register callbacks and populate initial state."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SMOOTHING_CONFIG.format(self._device_id),
                self._update_smoothing_type,
            )
        )
        self._update_smoothing_type()

    @callback
    def _update_smoothing_type(self, _: dict[str, Any] | None = None) -> None:
        """Update smoothing type selection."""
        if self._client.smoothing:
            option = self._client.smoothing.get(
                hyperhdr_const.KEY_SMOOTHING_TYPE_CONFIG
            )
            if option in self._attr_options:
                self._attr_current_option = option
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Set smoothing type."""
        await async_patch_smoothing_config(
            self.hass,
            self._entry_id,
            self._server_id,
            self._instance_num,
            **{hyperhdr_const.KEY_SMOOTHING_TYPE_CONFIG: option},
        )
