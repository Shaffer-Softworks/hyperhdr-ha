#!/usr/bin/env python3
"""Docker E2E test for issue #99 solid color brightness scaling."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import websockets
from hyperhdr import client, const as hyperhdr_const


def _priority_rgb(priorities: list[dict], level: int) -> list[int] | None:
    for entry in priorities or []:
        if entry.get(hyperhdr_const.KEY_PRIORITY) != level:
            continue
        if entry.get(hyperhdr_const.KEY_COMPONENTID) != hyperhdr_const.KEY_COMPONENTID_COLOR:
            continue
        value = entry.get(hyperhdr_const.KEY_VALUE) or {}
        rgb = value.get(hyperhdr_const.KEY_RGB)
        if rgb is not None:
            return list(rgb)
    return None


def _scale_rgb(rgb: list[int], brightness: int) -> list[int]:
    if brightness >= 255:
        return list(rgb)
    scale = brightness / 255.0
    return [min(255, int(round(channel * scale))) for channel in rgb]


async def _ha_call_service(
    ws,
    msg_id: int,
    domain: str,
    service: str,
    entity_id: str,
    service_data: dict | None = None,
) -> tuple[int, dict]:
    payload: dict = {
        "id": msg_id,
        "type": "call_service",
        "domain": domain,
        "service": service,
        "target": {"entity_id": [entity_id]},
    }
    if service_data:
        payload["service_data"] = service_data
    await ws.send(json.dumps(payload))
    return msg_id + 1, json.loads(await ws.recv())


async def _ha_get_state(ws, msg_id: int, entity_id: str) -> tuple[int, dict]:
    await ws.send(
        json.dumps(
            {
                "id": msg_id,
                "type": "get_states",
            }
        )
    )
    msg_id += 1
    response = json.loads(await ws.recv())
    for state in response.get("result", []):
        if state.get("entity_id") == entity_id:
            return msg_id, state
    return msg_id, {}


async def _ha_connect(
    ha_host: str,
    ha_port: int,
    ha_username: str | None,
    ha_password: str | None,
    ha_access_token: str | None,
):
    uri = f"ws://{ha_host}:{ha_port}/api/websocket"
    ws = await websockets.connect(uri)
    await ws.recv()
    if ha_access_token:
        await ws.send(json.dumps({"type": "auth", "access_token": ha_access_token}))
    else:
        await ws.send(
            json.dumps({"type": "auth", "username": ha_username, "password": ha_password})
        )
    auth = json.loads(await ws.recv())
    if auth.get("type") != "auth_ok":
        await ws.close()
        raise RuntimeError(f"HA auth failed: {auth}")
    return ws


async def _hyperhdr_connect(host: str, port: int, token: str | None) -> client.HyperHDRClient:
    hyperhdr_client = client.HyperHDRClient(host, port, token=token)
    if not await hyperhdr_client.async_client_connect():
        raise RuntimeError(f"cannot connect to HyperHDR {host}:{port}")
    if token is not None and not await hyperhdr_client.async_login(token=token):
        await hyperhdr_client.async_client_disconnect()
        raise RuntimeError("HyperHDR token login failed")
    await hyperhdr_client.async_sysinfo()
    return hyperhdr_client


async def _run(
    ha_host: str,
    ha_port: int,
    ha_username: str | None,
    ha_password: str | None,
    ha_access_token: str | None,
    hyperhdr_host: str,
    hyperhdr_port: int,
    hyperhdr_token: str | None,
    entity_id: str,
    priority: int,
) -> int:
    try:
        ws = await _ha_connect(
            ha_host, ha_port, ha_username, ha_password, ha_access_token
        )
    except RuntimeError as err:
        print(f"FAIL {err}")
        return 1
    print("OK HA auth")

    async with ws:
        msg_id = 1
        try:
            hyperhdr_client = await _hyperhdr_connect(
                hyperhdr_host, hyperhdr_port, hyperhdr_token
            )
        except RuntimeError as err:
            print(f"FAIL {err}")
            return 1
        try:
            print(f"Connected to HyperHDR, priority={priority}")

            # Step 1: Solid red at full brightness
            print("Step 1: turn_on Solid red brightness=255")
            msg_id, result = await _ha_call_service(
                ws,
                msg_id,
                "light",
                "turn_on",
                entity_id,
                {
                    "rgb_color": [255, 0, 0],
                    "brightness": 255,
                    "effect": "Solid",
                },
            )
            if not result.get("success"):
                print(f"FAIL turn_on full: {result}")
                return 1
            await asyncio.sleep(2)
            await hyperhdr_client.async_sysinfo()
            rgb = _priority_rgb(hyperhdr_client.priorities, priority)
            expected = [255, 0, 0]
            if rgb != expected:
                print(f"FAIL step 1 RGB: expected {expected}, got {rgb}")
                return 1
            print(f"OK step 1 RGB at priority {priority}: {rgb}")

            # Step 2: Dim to ~30% without changing color
            dim_brightness = 76
            print(f"Step 2: turn_on brightness={dim_brightness} only")
            msg_id, result = await _ha_call_service(
                ws,
                msg_id,
                "light",
                "turn_on",
                entity_id,
                {"brightness": dim_brightness},
            )
            if not result.get("success"):
                print(f"FAIL turn_on dim: {result}")
                return 1
            await asyncio.sleep(2)
            await hyperhdr_client.async_sysinfo()
            rgb = _priority_rgb(hyperhdr_client.priorities, priority)
            expected = _scale_rgb([255, 0, 0], dim_brightness)
            if rgb != expected:
                print(
                    f"FAIL step 2 RGB: expected scaled {expected}, got {rgb}"
                )
                return 1
            print(f"OK step 2 dimmed RGB: {rgb}")

            msg_id, state = await _ha_get_state(ws, msg_id, entity_id)
            ha_brightness = state.get("attributes", {}).get("brightness")
            if ha_brightness != dim_brightness:
                print(
                    f"WARN HA brightness attribute: expected {dim_brightness}, "
                    f"got {ha_brightness}"
                )
            else:
                print(f"OK HA brightness attribute: {ha_brightness}")

            # Step 3: Brighten back to 100%
            print("Step 3: turn_on brightness=255")
            msg_id, result = await _ha_call_service(
                ws,
                msg_id,
                "light",
                "turn_on",
                entity_id,
                {"brightness": 255},
            )
            if not result.get("success"):
                print(f"FAIL turn_on bright: {result}")
                return 1
            await asyncio.sleep(2)
            await hyperhdr_client.async_sysinfo()
            rgb = _priority_rgb(hyperhdr_client.priorities, priority)
            expected = [255, 0, 0]
            if rgb != expected:
                print(f"FAIL step 3 RGB: expected {expected}, got {rgb}")
                return 1
            print(f"OK step 3 restored RGB: {rgb}")

            # Step 4: Color at partial brightness
            mid_brightness = 128
            print(f"Step 4: turn_on blue brightness={mid_brightness}")
            msg_id, result = await _ha_call_service(
                ws,
                msg_id,
                "light",
                "turn_on",
                entity_id,
                {
                    "rgb_color": [0, 0, 255],
                    "brightness": mid_brightness,
                    "effect": "Solid",
                },
            )
            if not result.get("success"):
                print(f"FAIL turn_on blue: {result}")
                return 1
            await asyncio.sleep(2)
            await hyperhdr_client.async_sysinfo()
            rgb = _priority_rgb(hyperhdr_client.priorities, priority)
            expected = _scale_rgb([0, 0, 255], mid_brightness)
            if rgb != expected:
                print(f"FAIL step 4 RGB: expected {expected}, got {rgb}")
                return 1
            print(f"OK step 4 partial brightness blue RGB: {rgb}")

            # Cleanup: turn off
            msg_id, result = await _ha_call_service(
                ws, msg_id, "light", "turn_off", entity_id
            )
            print(f"Cleanup turn_off: success={result.get('success')}")
        finally:
            await hyperhdr_client.async_client_disconnect()

    print("PASS: solid color brightness E2E (#99)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ha-host", default="127.0.0.1")
    parser.add_argument("--ha-port", type=int, default=8123)
    parser.add_argument("--ha-username", default="test")
    parser.add_argument("--ha-password")
    parser.add_argument("--ha-access-token")
    parser.add_argument("--hyperhdr-host", default="10.12.0.12")
    parser.add_argument("--hyperhdr-port", type=int, default=19444)
    parser.add_argument("--hyperhdr-token")
    parser.add_argument("--entity-id", default="light.basement_tv_strip")
    parser.add_argument("--priority", type=int, default=128)
    args = parser.parse_args()
    if not args.ha_access_token and not args.ha_password:
        parser.error("Provide --ha-access-token or --ha-password")
    return asyncio.run(
        _run(
            args.ha_host,
            args.ha_port,
            args.ha_username,
            args.ha_password,
            args.ha_access_token,
            args.hyperhdr_host,
            args.hyperhdr_port,
            args.hyperhdr_token,
            args.entity_id,
            args.priority,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
