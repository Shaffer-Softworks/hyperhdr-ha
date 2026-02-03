"""Camera platform for HyperHDR."""

from __future__ import annotations

import asyncio
import base64
import binascii
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import functools
import io
import json
import logging
from typing import Any

from aiohttp import ClientSession, WSMsgType, web
from PIL import Image
from hyperhdr import client
from hyperhdr.const import (
    KEY_IMAGE,
    KEY_IMAGE_STREAM,
    KEY_LEDCOLORS,
    KEY_RESULT,
    KEY_UPDATE,
)

from homeassistant.components.camera import (
    DEFAULT_CONTENT_TYPE,
    Camera,
    async_get_still_stream,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
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
                ),
                HyperHDRLedGradientCamera(
                    server_id,
                    instance_num,
                    instance_name,
                    host,
                    port_ws,
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
    """Camera entity for HyperHDR LED Colors stream."""

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
    ) -> None:
        """Initialize the LED camera."""
        super().__init__()
        self._attr_unique_id = get_hyperhdr_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_LED_CAMERA
        )
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._host = host
        self._port = port
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
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        await super().async_will_remove_from_hass()

    async def _stream_worker(self) -> None:
        """Background task to maintain WebSocket connection and update image."""
        url = f"ws://{self._host}:{self._port}/json-rpc"
        while True:
            try:
                async with ClientSession() as session:
                    # Use heartbeat to keep connection alive
                    async with session.ws_connect(url, heartbeat=30) as ws:
                        _LOGGER.debug(
                            "Connected to HyperHDR LED stream at %s", url
                        )
                        # Start video stream
                        await ws.send_json(
                            {
                                "command": "ledcolors",
                                "subcommand": "imagestream-start",
                                "tan": 1,
                            }
                        )
                        _LOGGER.debug("Sent imagestream-start command")

                        async for msg in ws:
                            if msg.type == WSMsgType.BINARY:
                                async with self._image_cond:
                                    self._last_image = msg.data
                                    self._image_cond.notify_all()
                            elif msg.type == WSMsgType.TEXT:
                                _LOGGER.debug("HyperHDR stream text: %s", msg.data)
                            elif msg.type == WSMsgType.CLOSED:
                                _LOGGER.warning("HyperHDR stream connection closed")
                                break
                            elif msg.type == WSMsgType.ERROR:
                                _LOGGER.error(
                                    "HyperHDR LED stream error: %s", msg.data
                                )
                                break
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.error("HyperHDR LED stream connection failed: %s", err)

            _LOGGER.debug("Stream worker waiting 5s before reconnect...")
            await asyncio.sleep(5)

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
    """Camera entity for HyperHDR LED Gradient stream."""

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
    ) -> None:
        """Initialize the LED camera."""
        super().__init__()
        self._attr_unique_id = get_hyperhdr_unique_id(
            server_id, instance_num, TYPE_HYPERHDR_LED_GRADIENT_CAMERA
        )
        self._device_id = get_hyperhdr_device_id(server_id, instance_num)
        self._host = host
        self._port = port
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
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        await super().async_will_remove_from_hass()

    async def _stream_worker(self) -> None:
        """Background task to maintain WebSocket connection and update image."""
        url = f"ws://{self._host}:{self._port}/json-rpc"
        while True:
            try:
                async with ClientSession() as session:
                    # Use heartbeat to keep connection alive
                    async with session.ws_connect(url, heartbeat=30) as ws:
                        _LOGGER.debug(
                            "Connected to HyperHDR LED gradient stream at %s", url
                        )
                        # Start video stream
                        await ws.send_json(
                            {
                                "command": "ledcolors",
                                "subcommand": "ledstream-start",
                                "tan": 1,
                            }
                        )
                        _LOGGER.debug("Sent ledstream-start command")

                        async for msg in ws:
                            if msg.type == WSMsgType.BINARY:
                                # Convert binary RGB data to 1D image
                                try:
                                    # Assuming data is simple RGB flat array
                                    # Width = len(data) / 3
                                    data = msg.data
                                    total_leds = len(data) // 3
                                    if len(data) % 3 != 0:
                                        _LOGGER.warning(
                                            "Received incomplete LED data: %d bytes",
                                            len(data),
                                        )
                                        continue

                                    # Create 1D image with some height (e.g., 20px) to make it visible in UI
                                    img = Image.frombytes(
                                        "RGB", (total_leds, 1), data
                                    )
                                    if total_leds > 0:
                                        img = img.resize((total_leds, 20), Image.Resampling.NEAREST)

                                    # Save to bytes
                                    img_byte_arr = io.BytesIO()
                                    img.save(img_byte_arr, format="JPEG")
                                    
                                    async with self._image_cond:
                                        self._last_image = img_byte_arr.getvalue()
                                        self._image_cond.notify_all()
                                        
                                except Exception as err:
                                    _LOGGER.error("Error processing LED gradient: %s", err)
                                    
                            elif msg.type == WSMsgType.TEXT:
                                try:
                                    json_data = json.loads(msg.data)
                                    if json_data.get("command") == "ledcolors-ledstream-update":
                                        leds = json_data.get("result", {}).get("leds")
                                        if leds:
                                            # Convert list of integers [R, G, B, ...] to bytes
                                            data = bytes(leds)
                                            total_leds = len(data) // 3
                                            
                                            # Create image and notify
                                            img = Image.frombytes("RGB", (total_leds, 1), data)
                                            if total_leds > 0:
                                                img = img.resize((total_leds, 20), Image.Resampling.NEAREST)
                                            
                                            img_byte_arr = io.BytesIO()
                                            img.save(img_byte_arr, format="JPEG")
                                            
                                            async with self._image_cond:
                                                self._last_image = img_byte_arr.getvalue()
                                                self._image_cond.notify_all()
                                                
                                    _LOGGER.debug("HyperHDR stream text: %s", msg.data)
                                except Exception as err:
                                    _LOGGER.error("Error parsing LED gradient JSON: %s", err)
                            elif msg.type == WSMsgType.CLOSED:
                                _LOGGER.warning("HyperHDR stream connection closed")
                                break
                            elif msg.type == WSMsgType.ERROR:
                                _LOGGER.error(
                                    "HyperHDR LED stream error: %s", msg.data
                                )
                                break
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.error("HyperHDR LED stream connection failed: %s", err)

            _LOGGER.debug("Stream worker waiting 5s before reconnect...")
            await asyncio.sleep(5)

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
