#!/usr/bin/env python3
"""Docker E2E regression: effect brightness still uses HyperHDR adjustment."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import websockets
from hyperhdr import client, const as hyperhdr_const


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
    await ws.send(json.dumps({"id": msg_id, "type": "get_states"}))
    msg_id += 1
    response = json.loads(await ws.recv())
    for state in response.get("result", []):
        if state.get("entity_id") == entity_id:
            return msg_id, state
    return msg_id, {}


async def _ha_connect(
    ha_host: str,
    ha_port: int,
    ha_access_token: str,
):
    uri = f"ws://{ha_host}:{ha_port}/api/websocket"
    ws = await websockets.connect(uri)
    await ws.recv()
    await ws.send(json.dumps({"type": "auth", "access_token": ha_access_token}))
    auth = json.loads(await ws.recv())
    if auth.get("type") != "auth_ok":
        await ws.close()
        raise RuntimeError(f"HA auth failed: {auth}")
    return ws


async def _hyperhdr_connect(host: str, port: int) -> client.HyperHDRClient:
    hyperhdr_client = client.HyperHDRClient(host, port)
    if not await hyperhdr_client.async_client_connect():
        raise RuntimeError(f"cannot connect to HyperHDR {host}:{port}")
    await hyperhdr_client.async_sysinfo()
    return hyperhdr_client


def _priority_effect(priorities: list[dict], level: int) -> dict | None:
    for entry in priorities or []:
        if entry.get(hyperhdr_const.KEY_PRIORITY) != level:
            continue
        if entry.get(hyperhdr_const.KEY_COMPONENTID) != hyperhdr_const.KEY_COMPONENTID_EFFECT:
            continue
        return entry
    return None


def _adjustment_brightness(adjustment: list[dict] | None) -> int | None:
    if not adjustment:
        return None
    item = adjustment[0] or {}
    if hyperhdr_const.KEY_BRIGHTNESS in item:
        pct = item[hyperhdr_const.KEY_BRIGHTNESS]
        return int(round((float(pct) * 255) / 100))
    if "luminanceGain" in item:
        try:
            gain = float(item["luminanceGain"])
        except (TypeError, ValueError):
            return None
        return int(round(min(gain, 1.0) * 255))
    return None


async def _run(
    ha_host: str,
    ha_port: int,
    ha_access_token: str,
    hyperhdr_host: str,
    hyperhdr_port: int,
    entity_id: str,
    priority: int,
    effect_name: str,
) -> int:
    try:
        ws = await _ha_connect(ha_host, ha_port, ha_access_token)
    except RuntimeError as err:
        print(f"FAIL {err}")
        return 1
    print("OK HA auth")

    async with ws:
        msg_id = 1
        try:
            hyperhdr_client = await _hyperhdr_connect(hyperhdr_host, hyperhdr_port)
        except RuntimeError as err:
            print(f"FAIL {err}")
            return 1
        try:
            print(f"Connected to HyperHDR, priority={priority}, effect={effect_name}")

            print(f"Step 1: turn_on effect '{effect_name}' brightness=255")
            msg_id, result = await _ha_call_service(
                ws,
                msg_id,
                "light",
                "turn_on",
                entity_id,
                {"effect": effect_name, "brightness": 255},
            )
            if not result.get("success"):
                print(f"FAIL turn_on effect: {result}")
                return 1
            await asyncio.sleep(2)
            await hyperhdr_client.async_sysinfo()

            effect_pri = _priority_effect(hyperhdr_client.priorities, priority)
            if not effect_pri:
                print(f"FAIL step 1: no EFFECT at priority {priority}")
                return 1
            owner = effect_pri.get(hyperhdr_const.KEY_OWNER)
            if owner != effect_name:
                print(f"FAIL step 1 effect name: expected {effect_name}, got {owner}")
                return 1
            adj_b = _adjustment_brightness(hyperhdr_client.adjustment)
            if adj_b is None or abs(adj_b - 255) > 5:
                print(f"FAIL step 1 adjustment brightness: expected ~255, got {adj_b}")
                return 1
            print(f"OK step 1 EFFECT '{owner}' active, adjustment brightness={adj_b}")

            dim = 76
            print(f"Step 2: turn_on brightness={dim} only (effect should stay)")
            msg_id, result = await _ha_call_service(
                ws, msg_id, "light", "turn_on", entity_id, {"brightness": dim}
            )
            if not result.get("success"):
                print(f"FAIL turn_on dim: {result}")
                return 1
            await asyncio.sleep(2)
            await hyperhdr_client.async_sysinfo()

            effect_pri = _priority_effect(hyperhdr_client.priorities, priority)
            if not effect_pri or effect_pri.get(hyperhdr_const.KEY_OWNER) != effect_name:
                print(f"FAIL step 2: effect not still active: {effect_pri}")
                return 1
            adj_b = _adjustment_brightness(hyperhdr_client.adjustment)
            if adj_b is None or abs(adj_b - dim) > 8:
                print(f"FAIL step 2 adjustment brightness: expected ~{dim}, got {adj_b}")
                return 1
            msg_id, state = await _ha_get_state(ws, msg_id, entity_id)
            ha_b = state.get("attributes", {}).get("brightness")
            if ha_b != dim:
                print(f"WARN HA brightness attribute: expected {dim}, got {ha_b}")
            else:
                print(f"OK HA brightness attribute: {ha_b}")
            print(f"OK step 2 dimmed adjustment brightness={adj_b}, effect still active")

            print("Step 3: turn_on brightness=255")
            msg_id, result = await _ha_call_service(
                ws, msg_id, "light", "turn_on", entity_id, {"brightness": 255}
            )
            if not result.get("success"):
                print(f"FAIL turn_on bright: {result}")
                return 1
            await asyncio.sleep(2)
            await hyperhdr_client.async_sysinfo()

            effect_pri = _priority_effect(hyperhdr_client.priorities, priority)
            if not effect_pri or effect_pri.get(hyperhdr_const.KEY_OWNER) != effect_name:
                print(f"FAIL step 3: effect not still active: {effect_pri}")
                return 1
            adj_b = _adjustment_brightness(hyperhdr_client.adjustment)
            if adj_b is None or abs(adj_b - 255) > 5:
                print(f"FAIL step 3 adjustment brightness: expected ~255, got {adj_b}")
                return 1
            print(f"OK step 3 restored adjustment brightness={adj_b}")

            msg_id, result = await _ha_call_service(
                ws, msg_id, "light", "turn_off", entity_id
            )
            print(f"Cleanup turn_off: success={result.get('success')}")
        finally:
            await hyperhdr_client.async_client_disconnect()

    print("PASS: effect brightness regression")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ha-host", default="127.0.0.1")
    parser.add_argument("--ha-port", type=int, default=8123)
    parser.add_argument("--ha-access-token", required=True)
    parser.add_argument("--hyperhdr-host", default="10.12.0.12")
    parser.add_argument("--hyperhdr-port", type=int, default=19444)
    parser.add_argument("--entity-id", default="light.basement_tv_strip")
    parser.add_argument("--priority", type=int, default=128)
    parser.add_argument("--effect", default="Rainbow swirl")
    args = parser.parse_args()
    return asyncio.run(
        _run(
            args.ha_host,
            args.ha_port,
            args.ha_access_token,
            args.hyperhdr_host,
            args.hyperhdr_port,
            args.entity_id,
            args.priority,
            args.effect,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
