"""Camera platform for HyperHDR."""

from __future__ import annotations

import asyncio
import functools
import logging
import shutil
import socket
import time
from typing import Any

from aiohttp import web
from hyperhdr.stream import (
    HyperHDRLedColorsStream,
    HyperHDRLedGradientStream,
)

from aiohttp.client_exceptions import ClientConnectionResetError
from homeassistant.components.camera import (
    DEFAULT_CONTENT_TYPE,
    Camera,
    CameraEntityFeature,
    async_get_still_stream,
)
from homeassistant.components.stream import CONF_USE_WALLCLOCK_AS_TIMESTAMPS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_TOKEN, CONTENT_TYPE_MULTIPART
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

# Home Assistant's stream worker remuxes into fMP4. It does not transcode, so a
# JPEG source is published as mp4v, which browsers and ExoPlayer will not play.
_H264_CONTENT_TYPE = "video/mp2t"
_H264_FRAME_RATE = 10
_FFMPEG_STDOUT_CHUNK = 65536
_FFMPEG_KILL_RETURN_CODE = -9
# HA's stream SOURCE_TIMEOUT is 30s. Keep ffmpeg fed even when LED JPEGs are
# identical or HyperHDR briefly pauses — async_get_still_stream skips equals.
_MJPEG_REPEAT_INTERVAL_S = 0.1
_FRAME_BOUNDARY = b"--frameboundary\r\n"


def _h264_ffmpeg_command(binary: str, mjpeg_url: str) -> list[str]:
    """Build ffmpeg argv that turns the localhost MJPEG into H.264 MPEG-TS."""
    # Even dimensions of at least 2px: libx264 rejects a 1px-tall LED image.
    video_filter = (
        f"fps={_H264_FRAME_RATE},"
        "scale=trunc(max(2\\,iw)/2)*2:trunc(max(2\\,ih)/2)*2"
    )
    return [
        binary,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostdin",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-use_wallclock_as_timestamps",
        "1",
        "-f",
        "mpjpeg",
        "-i",
        mjpeg_url,
        "-an",
        "-vf",
        video_filter,
        "-fps_mode",
        "cfr",
        "-r",
        str(_H264_FRAME_RATE),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "zerolatency",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "baseline",
        "-g",
        str(_H264_FRAME_RATE),
        "-keyint_min",
        str(_H264_FRAME_RATE),
        "-sc_threshold",
        "0",
        "-force_key_frames",
        "expr:gte(t,n_forced*1)",
        "-flush_packets",
        "1",
        "-muxdelay",
        "0",
        "-muxpreload",
        "0",
        "-f",
        "mpegts",
        "pipe:1",
    ]


def _ffmpeg_binary(hass: HomeAssistant) -> str | None:
    """Return the ffmpeg binary Home Assistant is configured to use."""
    from homeassistant.components.ffmpeg import get_ffmpeg_manager

    try:
        return get_ffmpeg_manager(hass).binary
    except (ValueError, KeyError):
        return shutil.which("ffmpeg")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a HyperHDR platform from config entry."""
    server_id = config_entry.unique_id
    host = config_entry.data[CONF_HOST]
    port_ws = config_entry.data.get(CONF_PORT_WS, 8090)
    token = config_entry.data.get(CONF_TOKEN)
    admin_password = config_entry.data.get(CONF_ADMIN_PASSWORD) or None

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
    def instance_add(
        instance_num: int, instance_name: str, sysinfo: dict[str, Any]
    ) -> None:
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


class _HyperHDRLedCameraBase(Camera):
    """Shared lazy-start WebSocket camera behavior."""

    _stream_task_name: str

    def __init__(self) -> None:
        """Initialize shared camera state."""
        super().__init__()
        self._last_image: bytes | None = None
        self._stream_task: asyncio.Task | None = None
        self._image_cond = asyncio.Condition()

    async def async_added_to_hass(self) -> None:
        """Register removal listener; do not open the stream yet."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ENTITY_REMOVE.format(self._attr_unique_id),
                functools.partial(self.async_remove, force_remove=True),
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        """Stop the background streaming task."""
        await self._stop_stream()
        await super().async_will_remove_from_hass()

    async def _stop_stream(self) -> None:
        """Stop WebSocket stream and background worker."""
        await self._led_stream.stop()
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        if self._attr_is_streaming:
            self._attr_is_streaming = False

    def _ensure_stream_started(self) -> None:
        """Start the background stream on first consumer demand."""
        if self._stream_task and not self._stream_task.done():
            return
        self._stream_task = self.hass.async_create_background_task(
            self._stream_worker(),
            self._stream_task_name,
        )

    async def _wait_for_image(self) -> bytes | None:
        """Wait for new image."""
        self._ensure_stream_started()
        async with self._image_cond:
            await self._image_cond.wait()
            return self._last_image

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the latest image, starting the stream if needed."""
        self._ensure_stream_started()
        return self._last_image

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        """Serve an HTTP MJPEG stream from the camera."""
        self._ensure_stream_started()
        return await async_get_still_stream(
            request,
            self._wait_for_image,
            DEFAULT_CONTENT_TYPE,
            0.0,
        )


class HyperHDRLedCamera(_HyperHDRLedCameraBase):
    """Camera entity for HyperHDR LED Colors stream.

    Uses HyperHDRLedColorsStream from hyperhdr.stream for WebSocket streaming
    with automatic reconnection and token/admin-password authentication.
    Stream starts lazily on first image/MJPEG request. STREAM/HLS is H.264:
    ffmpeg transcodes the localhost MJPEG into MPEG-TS, and Home Assistant's
    stream worker remuxes that to ``/api/hls/``.
    """

    _attr_has_entity_name = True
    _attr_name = "LED Colors"
    _attr_entity_registry_enabled_default = False
    _attr_supported_features = CameraEntityFeature.STREAM

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
        self._stream_task_name = f"hyperhdr_led_stream_{self._device_id}"
        self._led_stream = HyperHDRLedColorsStream(
            host,
            port,
            token=token,
            admin_password=admin_password,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=HYPERHDR_MANUFACTURER_NAME,
            model=HYPERHDR_MODEL_NAME,
            name=instance_name,
        )
        # Live LED JPEGs do not carry stable decode timestamps; wallclock keeps
        # the remuxer from stalling when frames are repeated for ffmpeg.
        self.stream_options[CONF_USE_WALLCLOCK_AS_TIMESTAMPS] = True
        self._local_runner: web.AppRunner | None = None
        self._local_site: web.BaseSite | None = None
        self._local_port: int | None = None
        self._h264_runner: web.AppRunner | None = None
        self._h264_site: web.BaseSite | None = None
        self._h264_port: int | None = None

    async def _ensure_local_mjpeg_server(self) -> str:
        """Start a loopback multipart MJPEG server for FFmpeg if needed."""
        if self._local_port is not None:
            return f"http://127.0.0.1:{self._local_port}/mjpeg"

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

            app = web.Application()
            app.router.add_get("/mjpeg", self._handle_local_mjpeg)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.SockSite(runner, sock)
            await site.start()
        except Exception:
            sock.close()
            raise

        self._local_runner = runner
        self._local_site = site
        self._local_port = port
        _LOGGER.debug(
            "LED Colors local MJPEG server listening on 127.0.0.1:%s", port
        )
        return f"http://127.0.0.1:{port}/mjpeg"

    async def _handle_local_mjpeg(self, request: web.Request) -> web.StreamResponse:
        """Serve multipart MJPEG for ffmpeg, repeating the last frame.

        ``async_get_still_stream`` skips identical JPEG bytes. Static or briefly
        paused LED colors then starve ffmpeg, and Home Assistant's stream worker
        hits its 30s source timeout (``Immediate exit requested``). Always write
        the latest buffer on a short interval so the H.264 pipe stays alive.
        """
        self._ensure_stream_started()
        response = web.StreamResponse()
        response.content_type = CONTENT_TYPE_MULTIPART.format("--frameboundary")
        await response.prepare(request)

        async with self._image_cond:
            while self._last_image is None:
                await self._image_cond.wait()
            image = self._last_image

        try:
            while True:
                assert image is not None
                await response.write(
                    _FRAME_BOUNDARY
                    + (
                        f"Content-Type: {DEFAULT_CONTENT_TYPE}\r\n"
                        f"Content-Length: {len(image)}\r\n\r\n"
                    ).encode()
                    + image
                    + b"\r\n"
                )
                async with self._image_cond:
                    try:
                        await asyncio.wait_for(
                            self._image_cond.wait(),
                            timeout=_MJPEG_REPEAT_INTERVAL_S,
                        )
                    except TimeoutError:
                        pass
                    if self._last_image is not None:
                        image = self._last_image
        except (ClientConnectionResetError, ConnectionResetError):
            # ffmpeg disconnects when the stream worker restarts or stops.
            pass
        return response

    async def _ensure_h264_server(self) -> str | None:
        """Serve ffmpeg's H.264 MPEG-TS on loopback for the stream worker."""
        if self._h264_port is not None:
            return f"http://127.0.0.1:{self._h264_port}/stream.ts"
        if _ffmpeg_binary(self.hass) is None:
            _LOGGER.error(
                "ffmpeg is not available; LED Colors cannot publish an H.264 stream"
            )
            return None
        await self._ensure_local_mjpeg_server()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            app = web.Application()
            app.router.add_get("/stream.ts", self._handle_h264)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.SockSite(runner, sock)
            await site.start()
        except Exception:
            sock.close()
            raise

        self._h264_runner = runner
        self._h264_site = site
        self._h264_port = port
        _LOGGER.debug("LED Colors H.264 server listening on 127.0.0.1:%s", port)
        return f"http://127.0.0.1:{port}/stream.ts"

    async def _handle_h264(self, request: web.Request) -> web.StreamResponse:
        """Transcode the MJPEG buffer to H.264 MPEG-TS for one stream client."""
        binary = _ffmpeg_binary(self.hass)
        if binary is None or self._local_port is None:
            raise web.HTTPServiceUnavailable

        process = await asyncio.create_subprocess_exec(
            *_h264_ffmpeg_command(
                binary, f"http://127.0.0.1:{self._local_port}/mjpeg"
            ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        stderr_task = asyncio.create_task(
            process.stderr.read(), name=f"hyperhdr_ffmpeg_stderr_{self._device_id}"
        )
        response = web.StreamResponse()
        response.content_type = _H264_CONTENT_TYPE
        try:
            await response.prepare(request)
            while True:
                chunk = await process.stdout.read(_FFMPEG_STDOUT_CHUNK)
                if not chunk:
                    break
                await response.write(chunk)
        except (ClientConnectionResetError, ConnectionResetError):
            # Stream worker closed the HTTP client (idle timeout / restart).
            pass
        finally:
            if process.returncode is None:
                process.kill()
                await asyncio.shield(process.wait())
            stderr = (
                (await asyncio.shield(stderr_task))
                .decode("utf-8", errors="replace")
                .strip()
            )
            # A viewer disconnect kills ffmpeg on purpose. Log only a real failure.
            if process.returncode not in (0, None, _FFMPEG_KILL_RETURN_CODE):
                _LOGGER.warning(
                    "LED Colors ffmpeg exited %s: %s",
                    process.returncode,
                    stderr or "(no stderr)",
                )
        return response

    async def _stop_h264_server(self) -> None:
        """Tear down the loopback H.264 server."""
        if self._h264_site is not None:
            await self._h264_site.stop()
            self._h264_site = None
        if self._h264_runner is not None:
            await self._h264_runner.cleanup()
            self._h264_runner = None
        self._h264_port = None

    async def stream_source(self) -> str | None:
        """Return a localhost H.264 MPEG-TS URL for the HA stream worker."""
        return await self._ensure_h264_server()

    async def _async_get_supported_webrtc_provider(self, fn):  # noqa: ANN001
        """Keep the frontend on HLS; do not hand this camera to go2rtc.

        go2rtc only auto-wraps ``generic`` camera HTTP sources with
        ``ffmpeg:``. Our MPEG-TS URL is otherwise registered as raw HTTP,
        which cannot feed WebRTC and fails with an RTSP DESCRIBE 404. HLS via
        the stream worker is the live path for tablets, Lovelace, and
        ``camera.record``.
        """
        return None

    async def _stop_local_mjpeg_server(self) -> None:
        """Tear down the loopback MJPEG server."""
        if self._local_site is not None:
            await self._local_site.stop()
            self._local_site = None
        if self._local_runner is not None:
            await self._local_runner.cleanup()
            self._local_runner = None
        self._local_port = None

    async def async_will_remove_from_hass(self) -> None:
        """Stop WebSocket stream and the loopback MJPEG and H.264 servers."""
        await self._stop_h264_server()
        await super().async_will_remove_from_hass()
        await self._stop_local_mjpeg_server()

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


class HyperHDRLedGradientCamera(_HyperHDRLedCameraBase):
    """Camera entity for HyperHDR LED Gradient stream.

    Uses HyperHDRLedGradientStream from hyperhdr.stream for WebSocket streaming
    with automatic reconnection, token/admin-password authentication, and
    built-in RGB-to-JPEG conversion via Pillow. Stream starts lazily on first
    image/MJPEG request.
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
        self._stream_task_name = f"hyperhdr_led_gradient_stream_{self._device_id}"
        self._led_stream = HyperHDRLedGradientStream(
            host,
            port,
            token=token,
            admin_password=admin_password,
            convert_to_jpeg=True,
            jpeg_height=20,
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=HYPERHDR_MANUFACTURER_NAME,
            model=HYPERHDR_MODEL_NAME,
            name=instance_name,
        )

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


CAMERA_TYPES = {
    TYPE_HYPERHDR_LED_CAMERA: HyperHDRLedCamera,
    TYPE_HYPERHDR_LED_GRADIENT_CAMERA: HyperHDRLedGradientCamera,
}
