"""Camera platform for HyperHDR."""

from __future__ import annotations

import asyncio
import base64
import binascii
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import functools
import logging
from typing import Any

from aiohttp import web
from hyperhdr import client
from hyperhdr.const import (
    KEY_IMAGE,
    KEY_IMAGE_STREAM,
    KEY_LEDCOLORS,
    KEY_RESULT,
    KEY_UPDATE,
)
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
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
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
    SIGNAL_ENTITY_REMOVE,
    TYPE_HYPERHDR_CAMERA,
    TYPE_HYPERHDR_LED_CAMERA,
    TYPE_HYPERHDR_LED_GRADIENT_CAMERA,
)

_LOGGER = logging.getLogger(__name__)

IMAGE_STREAM_JPG_SENTINEL = "data:image/jpg;base64,"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a HyperHDR platform from config entry."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    server_id = config_entry.unique_id
    host = config_entry.data[CONF_HOST]
    port = config_entry.data[CONF_PORT]
    port_ws = config_entry.data.get(CONF_PORT_WS, 8090)
    token = config_entry.data.get(CONF_TOKEN)
    admin_password = config_entry.data.get(CONF_ADMIN_PASSWORD)

    def camera_unique_id(instance_num: int) -> str:
        """Return the camera unique_id."""
        assert server_id
        return get_hyperhdr_unique_id(server_id, instance_num, TYPE_HYPERHDR_CAMERA)

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
                HyperHDRCamera(
                    server_id,
                    instance_num,
                    instance_name,
                    entry_data[CONF_INSTANCE_CLIENTS][instance_num],
                ),
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
                camera_unique_id(instance_num),
            ),
        )
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


# A note on HyperHDR streaming semantics:
#
# Different HyperHDR priorities behave different with regards to streaming. Colors will
# not stream (as there is nothing to stream). External grabbers (e.g. USB Capture) will
# stream what is being captured. Some effects (based on GIFs) will stream, others will
# not. In cases when streaming is not supported from a selected priority, there is no
# notification beyond the failure of new frames to arrive.


class HyperHDRCamera(Camera):
    """ComponentBinarySwitch switch class."""

    # The camera component does not work and is being disabled by default.
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        server_id: str,
        instance_num: int,
        instance_name: str,
        hyperhdr_client: client.HyperHDRClient,
    ) -> None:
        """Initialize the switch."""
        super().__init__()

        self._attr_unique_id = get_hyperhdr_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_CAMERA
        )
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._instance_name = instance_name
        self._client = hyperhdr_client

        self._image_cond = asyncio.Condition()
        self._image: bytes | None = None

        # The number of open streams, when zero the stream is stopped.
        self._image_stream_clients = 0

        self._client_callbacks = {
            f"{KEY_LEDCOLORS}-{KEY_IMAGE_STREAM}-{KEY_UPDATE}": self._update_imagestream
        }
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=HYPERHDR_MANUFACTURER_NAME,
            model=HYPERHDR_MODEL_NAME,
            name=instance_name,
            configuration_url=hyperhdr_client.remote_url,
        )

    @property
    def is_on(self) -> bool:
        """Return true if the camera is on."""
        return self.available

    @property
    def available(self) -> bool:
        """Return server availability."""
        return bool(self._client.has_loaded_state)

    async def _update_imagestream(self, img: dict[str, Any] | None = None) -> None:
        """Update HyperHDR image stream."""
        if not img:
            return
        img_data = img.get(KEY_RESULT, {}).get(KEY_IMAGE)
        if not img_data or not img_data.startswith(IMAGE_STREAM_JPG_SENTINEL):
            return
        async with self._image_cond:
            try:
                self._image = base64.b64decode(
                    img_data.removeprefix(IMAGE_STREAM_JPG_SENTINEL)
                )
                _LOGGER.debug("Camera image stream updated: %d bytes", len(self._image))
            except binascii.Error as e:
                _LOGGER.warning("Failed to decode camera image: %s", e)
                return
            self._image_cond.notify_all()

    async def _async_wait_for_camera_image(self) -> bytes | None:
        """Return a single camera image in a stream."""
        async with self._image_cond:
            await self._image_cond.wait()
            return self._image if self.available else None

    async def _start_image_streaming_for_client(self) -> bool:
        """Start streaming for a client."""
        if self._image_stream_clients == 0:
            _LOGGER.debug("Starting image stream for HyperHDR camera")
            if not await self._client.async_send_image_stream_start():
                _LOGGER.error("Failed to start HyperHDR image stream")
                return False

        self._image_stream_clients += 1
        self._attr_is_streaming = True
        self.async_write_ha_state()
        _LOGGER.debug("Image stream clients: %d", self._image_stream_clients)
        return True

    async def _stop_image_streaming_for_client(self) -> None:
        """Stop streaming for a client."""
        self._image_stream_clients -= 1
        _LOGGER.debug("Image stream clients: %d", self._image_stream_clients)

        if not self._image_stream_clients:
            _LOGGER.debug("Stopping image stream for HyperHDR camera")
            await self._client.async_send_image_stream_stop()
            self._attr_is_streaming = False
            self.async_write_ha_state()

    @asynccontextmanager
    async def _image_streaming(self) -> AsyncGenerator:
        """Async context manager to start/stop image streaming."""
        try:
            yield await self._start_image_streaming_for_client()
        finally:
            await self._stop_image_streaming_for_client()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return single camera image bytes."""
        async with self._image_streaming() as is_streaming:
            if is_streaming:
                return await self._async_wait_for_camera_image()
        return None

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        """Serve an HTTP MJPEG stream from the camera."""
        async with self._image_streaming() as is_streaming:
            if is_streaming:
                return await async_get_still_stream(
                    request,
                    self._async_wait_for_camera_image,
                    DEFAULT_CONTENT_TYPE,
                    0.0,
                )
        return None

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
        async for frame in self._led_stream.frames():
            if frame.image:
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

CAMERA_TYPES = {
    TYPE_HYPERHDR_CAMERA: HyperHDRCamera,
    TYPE_HYPERHDR_LED_CAMERA: HyperHDRLedCamera,
    TYPE_HYPERHDR_LED_GRADIENT_CAMERA: HyperHDRLedGradientCamera,
}
