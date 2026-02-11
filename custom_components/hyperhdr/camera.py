"""Camera platform for HyperHDR."""

from __future__ import annotations

import asyncio
import functools
import logging
import time

from aiohttp import web
from hyperhdr.stream import (
    HyperHDRLedColorsStream,
    HyperHDRLedGradientStream,
)

from homeassistant.components.camera import (
    DEFAULT_CONTENT_TYPE,
    Camera,
    async_get_still_stream,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_TOKEN
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
    CONF_PORT_WS,
    DOMAIN,
    HYPERHDR_MANUFACTURER_NAME,
    HYPERHDR_MODEL_NAME,
    SIGNAL_AVERAGE_COLOR,
    SIGNAL_ENTITY_REMOVE,
    TYPE_HYPERHDR_LED_CAMERA,
    TYPE_HYPERHDR_LED_GRADIENT_CAMERA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a HyperHDR platform from config entry."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    server_id = config_entry.unique_id
    host = config_entry.data[CONF_HOST]
    port_ws = config_entry.data.get(CONF_PORT_WS, 8090)
    token = config_entry.data.get(CONF_TOKEN)
    admin_password = config_entry.data.get(CONF_ADMIN_PASSWORD)

    def led_camera_unique_id(instance_num: int) -> str:
        """Return the led camera unique_id."""
        assert server_id
        return get_hyperhdr_unique_id(server_id, instance_num, TYPE_HYPERHDR_LED_CAMERA)

    def led_gradient_unique_id(instance_num: int) -> str:
        """Return the led gradient camera unique_id."""
        assert server_id
        return get_hyperhdr_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_LED_GRADIENT_CAMERA
        )

    @callback
    def instance_add(instance_num: int, instance_name: str) -> None:
        """Add entities for a new HyperHDR instance."""
        assert server_id

        # When admin_password is provided, use it as the primary auth for
        # WebSocket streams.  The library's _authorize_ws returns immediately
        # after a successful token login without escalating to admin, but
        # imagestream-start requires admin-level privileges.  By omitting the
        # token when an admin password is available we force the library to
        # authenticate with the admin password directly.
        stream_token = token if not admin_password else None

        async_add_entities(
            [
                HyperHDRLedCamera(
                    server_id,
                    instance_num,
                    instance_name,
                    host,
                    port_ws,
                    token=stream_token,
                    admin_password=admin_password,
                ),
                HyperHDRLedGradientCamera(
                    server_id,
                    instance_num,
                    instance_name,
                    host,
                    port_ws,
                    token=stream_token,
                    admin_password=admin_password,
                ),
            ]
        )

    @callback
    def instance_remove(instance_num: int) -> None:
        """Remove entities for an old HyperHDR instance."""
        assert server_id
        async_dispatcher_send(
            hass,
            SIGNAL_ENTITY_REMOVE.format(
                led_camera_unique_id(instance_num),
            ),
        )
        async_dispatcher_send(
            hass,
            SIGNAL_ENTITY_REMOVE.format(
                led_gradient_unique_id(instance_num),
            ),
        )

    listen_for_instance_updates(hass, config_entry, instance_add, instance_remove)


class HyperHDRLedCamera(Camera):
    """Camera entity for HyperHDR LED Colors stream.

    Uses HyperHDRLedColorsStream from hyperhdr.stream for WebSocket streaming
    with automatic reconnection and token/admin-password authentication.
    """

    _attr_has_entity_name = True
    _attr_name = "LED Colors"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        host: str,
        port: int,
        *,
        token: str | None = None,
        admin_password: str | None = None,
    ) -> None:
        """Initialize the LED camera."""
        super().__init__()
        self._attr_unique_id = get_hyperhdr_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_LED_CAMERA
        )
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._led_stream = HyperHDRLedColorsStream(
            host,
            port,
            token=token,
            admin_password=admin_password,
        )
        self._last_image: bytes | None = None
        self._stream_task: asyncio.Task | None = None
        self._image_cond = asyncio.Condition()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=HYPERHDR_MANUFACTURER_NAME,
            model=HYPERHDR_MODEL_NAME,
            name=instance_name,
        )

    async def async_added_to_hass(self) -> None:
        """Start the background streaming task."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ENTITY_REMOVE.format(self._attr_unique_id),
                functools.partial(self.async_remove, force_remove=True),
            )
        )
        self._stream_task = self.hass.async_create_background_task(
            self._stream_worker(),
            f"hyperhdr_led_stream_{self._device_id}",
        )

    async def async_will_remove_from_hass(self) -> None:
        """Stop the background streaming task."""
        await self._led_stream.stop()
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        await super().async_will_remove_from_hass()

    async def _stream_worker(self) -> None:
        """Background task to receive stream frames and update the camera image."""
        async for frame in self._led_stream.frames():
            if frame.image:
                if not self._attr_is_streaming:
                    self._attr_is_streaming = True
                    self.async_write_ha_state()
                async with self._image_cond:
                    self._last_image = frame.image
                    self._image_cond.notify_all()

    async def _wait_for_image(self) -> bytes | None:
        """Wait for new image."""
        async with self._image_cond:
            await self._image_cond.wait()
            return self._last_image

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the latest image."""
        return self._last_image

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        """Serve an HTTP MJPEG stream from the camera."""
        return await async_get_still_stream(
            request,
            self._wait_for_image,
            DEFAULT_CONTENT_TYPE,
            0.0,
        )


class HyperHDRLedGradientCamera(Camera):
    """Camera entity for HyperHDR LED Gradient stream.

    Uses HyperHDRLedGradientStream from hyperhdr.stream for WebSocket streaming
    with automatic reconnection, token/admin-password authentication, and
    built-in RGB-to-JPEG conversion via Pillow.
    """

    _attr_has_entity_name = True
    _attr_name = "LED Gradient"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        host: str,
        port: int,
        *,
        token: str | None = None,
        admin_password: str | None = None,
    ) -> None:
        """Initialize the LED gradient camera."""
        super().__init__()
        self._attr_unique_id = get_hyperhdr_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_LED_GRADIENT_CAMERA
        )
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._led_stream = HyperHDRLedGradientStream(
            host,
            port,
            token=token,
            admin_password=admin_password,
            convert_to_jpeg=True,
            jpeg_height=20,
        )
        self._last_image: bytes | None = None
        self._stream_task: asyncio.Task | None = None
        self._image_cond = asyncio.Condition()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=HYPERHDR_MANUFACTURER_NAME,
            model=HYPERHDR_MODEL_NAME,
            name=instance_name,
        )

    async def async_added_to_hass(self) -> None:
        """Start the background streaming task."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ENTITY_REMOVE.format(self._attr_unique_id),
                functools.partial(self.async_remove, force_remove=True),
            )
        )
        self._stream_task = self.hass.async_create_background_task(
            self._stream_worker(),
            f"hyperhdr_led_gradient_stream_{self._device_id}",
        )

    async def async_will_remove_from_hass(self) -> None:
        """Stop the background streaming task."""
        await self._led_stream.stop()
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        await super().async_will_remove_from_hass()

    async def _stream_worker(self) -> None:
        """Background task to receive stream frames and update the camera image."""
        # Throttle average-color dispatches to avoid flooding the HA event bus
        # and recorder.  The LED stream can run at 25-60 FPS; we only need to
        # update the sensor every couple of seconds.
        _AVG_COLOR_INTERVAL = 2.0  # seconds between dispatches
        _last_avg_dispatch: float = 0.0

        async for frame in self._led_stream.frames():
            if frame.image:
                if not self._attr_is_streaming:
                    self._attr_is_streaming = True
                    self.async_write_ha_state()
                async with self._image_cond:
                    self._last_image = frame.image
                    self._image_cond.notify_all()

            # Compute average color from raw LED data and dispatch for sensors.
            # Throttled to once per _AVG_COLOR_INTERVAL to avoid spamming.
            now = time.monotonic()
            if (
                frame.raw
                and len(frame.raw) >= 3
                and len(frame.raw) % 3 == 0
                and (now - _last_avg_dispatch) >= _AVG_COLOR_INTERVAL
            ):
                total_leds = len(frame.raw) // 3
                r_sum = g_sum = b_sum = 0
                for i in range(0, len(frame.raw), 3):
                    r_sum += frame.raw[i]
                    g_sum += frame.raw[i + 1]
                    b_sum += frame.raw[i + 2]
                avg_rgb = [
                    r_sum // total_leds,
                    g_sum // total_leds,
                    b_sum // total_leds,
                ]
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_AVERAGE_COLOR.format(self._device_id),
                    avg_rgb,
                )
                _last_avg_dispatch = now

    async def _wait_for_image(self) -> bytes | None:
        """Wait for new image."""
        async with self._image_cond:
            await self._image_cond.wait()
            return self._last_image

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the latest image."""
        return self._last_image

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        """Serve an HTTP MJPEG stream from the camera."""
        return await async_get_still_stream(
            request,
            self._wait_for_image,
            DEFAULT_CONTENT_TYPE,
            0.0,
        )


CAMERA_TYPES = {
    TYPE_HYPERHDR_LED_CAMERA: HyperHDRLedCamera,
    TYPE_HYPERHDR_LED_GRADIENT_CAMERA: HyperHDRLedGradientCamera,
}
