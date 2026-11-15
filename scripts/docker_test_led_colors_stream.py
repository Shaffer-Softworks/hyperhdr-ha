#!/usr/bin/env python3
"""Docker E2E test for LED Colors STREAM / HLS via localhost MJPEG."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urljoin

import websockets

CAMERA_ENTITY_FEATURE_STREAM = 2


async def _ha_connect(ha_host: str, ha_port: int, access_token: str):
    uri = f"ws://{ha_host}:{ha_port}/api/websocket"
    ws = await websockets.connect(uri)
    await ws.recv()
    await ws.send(json.dumps({"type": "auth", "access_token": access_token}))
    auth = json.loads(await ws.recv())
    if auth.get("type") != "auth_ok":
        await ws.close()
        raise RuntimeError(f"HA auth failed: {auth}")
    return ws


async def _ws_send(ws, msg_id: int, payload: dict) -> tuple[int, dict]:
    payload = {**payload, "id": msg_id}
    await ws.send(json.dumps(payload))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == msg_id:
            return msg_id + 1, msg


def _http_get(url: str, token: str, timeout: float = 30.0) -> tuple[int, bytes, str]:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Encoding": "identity",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(65536)
            encoding = (resp.headers.get("Content-Encoding") or "").lower()
            if encoding == "gzip" or body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            return resp.status, body, resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as err:
        body = err.read(4096) if err.fp else b""
        return err.code, body, err.headers.get("Content-Type", "") if err.headers else ""


def _media_playlist_url(master_url: str, master_body: str) -> str | None:
    """Resolve the media playlist URI from an HLS master playlist."""
    for line in master_body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return urljoin(master_url, line)
    return None


async def _run(
    ha_host: str,
    ha_port: int,
    access_token: str,
    led_colors_entity: str,
    led_gradient_entity: str,
) -> int:
    try:
        ws = await _ha_connect(ha_host, ha_port, access_token)
    except Exception as err:  # noqa: BLE001
        print(f"FAIL HA connect: {err}")
        return 1
    print("OK HA auth")

    base = f"http://{ha_host}:{ha_port}"
    async with ws:
        msg_id = 1

        msg_id, states_msg = await _ws_send(ws, msg_id, {"type": "get_states"})
        if not states_msg.get("success"):
            print(f"FAIL get_states: {states_msg}")
            return 1
        states = {s["entity_id"]: s for s in states_msg.get("result", [])}

        colors = states.get(led_colors_entity)
        gradient = states.get(led_gradient_entity)
        if not colors:
            print(f"FAIL missing entity {led_colors_entity}")
            return 1
        if not gradient:
            print(f"FAIL missing entity {led_gradient_entity}")
            return 1

        colors_features = int(colors.get("attributes", {}).get("supported_features") or 0)
        gradient_features = int(
            gradient.get("attributes", {}).get("supported_features") or 0
        )
        print(
            f"LED Colors state={colors.get('state')} "
            f"supported_features={colors_features}"
        )
        print(
            f"LED Gradient state={gradient.get('state')} "
            f"supported_features={gradient_features}"
        )

        if colors_features & CAMERA_ENTITY_FEATURE_STREAM == 0:
            print(
                "FAIL LED Colors missing CameraEntityFeature.STREAM "
                f"(got {colors_features})"
            )
            return 1
        print("OK LED Colors has STREAM feature")

        if gradient_features & CAMERA_ENTITY_FEATURE_STREAM:
            print(
                "FAIL LED Gradient should remain still-only "
                f"(supported_features={gradient_features})"
            )
            return 1
        print("OK LED Gradient has no STREAM feature")

        # Snapshot forces lazy WebSocket start; retry until first JPEG arrives.
        print("Waiting for camera snapshot JPEG...")
        jpeg: bytes | None = None
        for attempt in range(1, 31):
            status, body, ctype = _http_get(
                f"{base}/api/camera_proxy/{led_colors_entity}",
                access_token,
                timeout=15.0,
            )
            print(
                f"  snapshot attempt {attempt}: HTTP {status} "
                f"ctype={ctype!r} bytes={len(body)}"
            )
            if status == 200 and body[:2] == b"\xff\xd8":
                jpeg = body
                break
            await asyncio.sleep(2)
        if jpeg is None:
            print("FAIL snapshot never returned a JPEG")
            return 1
        print(f"OK snapshot JPEG ({len(jpeg)} bytes)")

        msg_id, states_msg = await _ws_send(ws, msg_id, {"type": "get_states"})
        colors = {
            s["entity_id"]: s for s in states_msg.get("result", [])
        }.get(led_colors_entity, {})
        print(f"LED Colors state after frames: {colors.get('state')}")

        # Ask HA stream worker for HLS. stream_source is H.264 MPEG-TS; a raw
        # JPEG source is remuxed as mp4v, which the tablet and browsers cannot play.
        print("Requesting camera/stream (HLS)...")
        msg_id, stream_msg = await _ws_send(
            ws,
            msg_id,
            {"type": "camera/stream", "entity_id": led_colors_entity},
        )
        if not stream_msg.get("success"):
            print(f"FAIL camera/stream: {stream_msg}")
            return 1
        result = stream_msg.get("result") or {}
        hls_url = result.get("url")
        if not hls_url:
            print(f"FAIL camera/stream missing url: {stream_msg}")
            return 1
        if "/api/hls/" not in hls_url:
            print(f"FAIL unexpected stream url: {hls_url}")
            return 1
        print(f"OK camera/stream url={hls_url}")

        # Master playlist is tiny; media segments live in the child playlist.
        status, body, ctype = _http_get(f"{base}{hls_url}", access_token, timeout=20.0)
        master_text = body.decode("utf-8", errors="replace")
        print(f"master playlist HTTP {status} ctype={ctype!r}:\n{master_text}")
        if status != 200 or "#EXTM3U" not in master_text:
            print("FAIL master playlist invalid")
            return 1
        if "avc1" not in master_text:
            print("FAIL master playlist is not H.264 (expected CODECS avc1)")
            return 1
        print("OK master playlist is H.264")
        media_url = _media_playlist_url(f"{base}{hls_url}", master_text)
        if not media_url:
            print("FAIL master playlist has no media URI")
            return 1
        print(f"OK media playlist url={media_url}")

        playlist = ""
        for attempt in range(1, 21):
            status, body, ctype = _http_get(media_url, access_token, timeout=20.0)
            text = body.decode("utf-8", errors="replace")
            has_media = "#EXTINF" in text or "#EXT-X-PART" in text
            print(
                f"  media playlist attempt {attempt}: HTTP {status} "
                f"ctype={ctype!r} bytes={len(body)} media={has_media}"
            )
            if status == 200 and "#EXTM3U" in text and has_media:
                playlist = text
                break
            await asyncio.sleep(2)

        if not playlist:
            print("FAIL HLS media playlist never became ready with segments")
            return 1
        print("OK HLS playlist contains media segments")
        print("--- playlist head ---")
        print("\n".join(playlist.splitlines()[:20]))
        print("--------------------")

        def _media_sequence(text: str) -> int | None:
            for line in text.splitlines():
                if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                    try:
                        return int(line.split(":", 1)[1].strip())
                    except ValueError:
                        return None
            return None

        # Stall regression: identical LED JPEGs used to starve ffmpeg until the
        # stream worker hit SOURCE_TIMEOUT (~30s) and demux failed. Sequence
        # must keep advancing while we hold the HLS URL open.
        first_seq = _media_sequence(playlist)
        print(f"Waiting for MEDIA-SEQUENCE to advance (start={first_seq})...")
        advanced = False
        for attempt in range(1, 25):
            await asyncio.sleep(2)
            status, body, _ctype = _http_get(media_url, access_token, timeout=20.0)
            text = body.decode("utf-8", errors="replace")
            seq = _media_sequence(text)
            print(f"  sequence poll {attempt}: HTTP {status} MEDIA-SEQUENCE={seq}")
            if (
                status == 200
                and first_seq is not None
                and seq is not None
                and seq > first_seq
            ):
                advanced = True
                break
        if not advanced:
            print("FAIL MEDIA-SEQUENCE did not advance (stream likely stalled)")
            return 1
        print("OK MEDIA-SEQUENCE advanced while stream stayed open")
        print("PASS LED Colors STREAM/HLS")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ha-host", default="127.0.0.1")
    parser.add_argument("--ha-port", type=int, default=8123)
    parser.add_argument("--ha-access-token", required=True)
    parser.add_argument(
        "--led-colors-entity",
        default="camera.basement_tv_strip_led_colors",
    )
    parser.add_argument(
        "--led-gradient-entity",
        default="camera.basement_tv_strip_led_gradient",
    )
    args = parser.parse_args()
    return asyncio.run(
        _run(
            args.ha_host,
            args.ha_port,
            args.ha_access_token,
            args.led_colors_entity,
            args.led_gradient_entity,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
