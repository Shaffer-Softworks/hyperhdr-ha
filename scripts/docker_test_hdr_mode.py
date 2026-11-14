#!/usr/bin/env python3
"""Docker E2E test for HDR Tone Mapping Mode select (Off / On / Auto).

Verifies against a live HyperHDR server that:
- Off/On map to videomodehdr 0/1
- Auto maps to automaticToneMapping.enable via config
- HA select.select_option drives the same behavior (when entity is available)
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from typing import Any

import websockets
from hyperhdr import client, const as hyperhdr_const

KEY_ATM = "automaticToneMapping"
KEY_ENABLE = "enable"


def _normalize_videomodehdr(mode: Any) -> str | None:
    if mode is True or mode == 1:
        return "On"
    if mode is False or mode == 0:
        return "Off"
    if mode == 2:
        return "Auto"
    return None


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
            json.dumps(
                {"type": "auth", "username": ha_username, "password": ha_password}
            )
        )
    auth = json.loads(await ws.recv())
    if auth.get("type") != "auth_ok":
        await ws.close()
        raise RuntimeError(f"HA auth failed: {auth}")
    return ws


async def _ws_request(ws, msg_id: int, payload: dict) -> tuple[int, dict]:
    payload = {**payload, "id": msg_id}
    await ws.send(json.dumps(payload))
    return msg_id + 1, json.loads(await ws.recv())


async def _ha_get_state(ws, msg_id: int, entity_id: str) -> tuple[int, dict]:
    msg_id, response = await _ws_request(ws, msg_id, {"type": "get_states"})
    for state in response.get("result", []) or []:
        if state.get("entity_id") == entity_id:
            return msg_id, state
    return msg_id, {}


async def _ha_find_entity(
    ws, msg_id: int, unique_id_suffix: str
) -> tuple[int, str | None]:
    msg_id, response = await _ws_request(
        ws, msg_id, {"type": "config/entity_registry/list"}
    )
    for entry in response.get("result", []) or []:
        uid = entry.get("unique_id") or ""
        if uid.endswith(unique_id_suffix) and entry.get("platform") == "hyperhdr":
            return msg_id, entry.get("entity_id")
    return msg_id, None


async def _ha_enable_entity(ws, msg_id: int, entity_id: str) -> tuple[int, dict]:
    return await _ws_request(
        ws,
        msg_id,
        {
            "type": "config/entity_registry/update",
            "entity_id": entity_id,
            "disabled_by": None,
        },
    )


async def _hyperhdr_connect(
    host: str, port: int, admin_password: str | None
) -> client.HyperHDRClient:
    hyperhdr_client = client.HyperHDRClient(host, port)
    if not await hyperhdr_client.async_client_connect():
        raise RuntimeError(f"cannot connect to HyperHDR {host}:{port}")
    await hyperhdr_client.async_get_serverinfo()
    if admin_password:
        login = await hyperhdr_client.async_login(password=admin_password)
        if not client.LoginResponseOK(login):
            await hyperhdr_client.async_client_disconnect()
            raise RuntimeError("HyperHDR admin login failed")
    return hyperhdr_client


async def _get_atm(hyperhdr_client: client.HyperHDRClient) -> dict[str, Any]:
    response = await hyperhdr_client.async_get_config()
    if not client.ResponseOK(response):
        raise RuntimeError(f"getconfig failed: {response}")
    assert response is not None
    atm = (response.get("info") or {}).get(KEY_ATM)
    if not isinstance(atm, dict):
        raise RuntimeError("automaticToneMapping missing from config")
    return copy.deepcopy(atm)


async def _set_atm_enable(
    hyperhdr_client: client.HyperHDRClient, atm: dict[str, Any], enable: bool
) -> dict[str, Any]:
    payload = {**atm, KEY_ENABLE: enable}
    response = await hyperhdr_client.async_set_config(config={KEY_ATM: payload})
    if not client.ResponseOK(response):
        raise RuntimeError(f"setconfig automaticToneMapping failed: {response}")
    return payload


async def _run_api_steps(
    hyperhdr_client: client.HyperHDRClient,
) -> tuple[dict[str, Any], bool]:
    """Exercise Off/On/Auto via HyperHDR APIs. Returns (atm, original_auto)."""
    atm = await _get_atm(hyperhdr_client)
    original_auto = bool(atm.get(KEY_ENABLE, False))
    print(
        f"API start: videomodehdr={hyperhdr_client.hdr_mode!r} "
        f"auto={original_auto}"
    )

    # Off
    if original_auto:
        atm = await _set_atm_enable(hyperhdr_client, atm, False)
    await hyperhdr_client.async_set_hdr_mode(**{hyperhdr_const.KEY_HDR: 0})
    await asyncio.sleep(0.4)
    await hyperhdr_client.async_get_serverinfo()
    mode = _normalize_videomodehdr(
        (hyperhdr_client.serverinfo or {}).get(hyperhdr_const.KEY_VIDEOMODE_HDR)
    )
    print(f"API Off: videomodehdr -> {mode}")
    if mode != "Off":
        raise RuntimeError(f"expected Off, got {mode}")

    # On
    await hyperhdr_client.async_set_hdr_mode(**{hyperhdr_const.KEY_HDR: 1})
    await asyncio.sleep(0.4)
    await hyperhdr_client.async_get_serverinfo()
    mode = _normalize_videomodehdr(
        (hyperhdr_client.serverinfo or {}).get(hyperhdr_const.KEY_VIDEOMODE_HDR)
    )
    print(f"API On: videomodehdr -> {mode}")
    if mode != "On":
        raise RuntimeError(f"expected On, got {mode}")

    # Auto
    atm = await _set_atm_enable(hyperhdr_client, atm, True)
    atm_check = await _get_atm(hyperhdr_client)
    print(f"API Auto: automaticToneMapping.enable={atm_check.get(KEY_ENABLE)}")
    if not atm_check.get(KEY_ENABLE):
        raise RuntimeError("expected automaticToneMapping.enable=True")

    return atm_check, original_auto


async def _run_ha_steps(
    ws,
    msg_id: int,
    entity_id: str,
    hyperhdr_client: client.HyperHDRClient,
) -> tuple[int, int]:
    """Drive select entity Off/On/Auto and verify HyperHDR state."""
    for option, check in (
        ("Off", "off"),
        ("On", "on"),
        ("Auto", "auto"),
    ):
        print(f"HA select_option -> {option}")
        msg_id, result = await _ws_request(
            ws,
            msg_id,
            {
                "type": "call_service",
                "domain": "select",
                "service": "select_option",
                "target": {"entity_id": [entity_id]},
                "service_data": {"option": option},
            },
        )
        if not result.get("success"):
            print(f"FAIL HA select_option {option}: {result}")
            return msg_id, 1
        await asyncio.sleep(1.5)
        await hyperhdr_client.async_get_serverinfo()
        atm = await _get_atm(hyperhdr_client)
        auto = bool(atm.get(KEY_ENABLE, False))
        mode = _normalize_videomodehdr(
            (hyperhdr_client.serverinfo or {}).get(hyperhdr_const.KEY_VIDEOMODE_HDR)
        )
        msg_id, state = await _ha_get_state(ws, msg_id, entity_id)
        ha_state = state.get("state")
        print(
            f"  HA state={ha_state!r} auto={auto} videomodehdr={mode} "
            f"raw={(hyperhdr_client.serverinfo or {}).get(hyperhdr_const.KEY_VIDEOMODE_HDR)!r}"
        )
        if check == "auto":
            if not auto:
                print("FAIL: Auto did not enable automaticToneMapping")
                return msg_id, 1
            if ha_state != "Auto":
                print(f"WARN HA state after Auto: {ha_state}")
        elif check == "off":
            if auto:
                print("FAIL: Off left automaticToneMapping enabled")
                return msg_id, 1
            if mode != "Off":
                print(f"FAIL: Off expected videomodehdr Off, got {mode}")
                return msg_id, 1
        elif check == "on":
            if auto:
                print("FAIL: On left automaticToneMapping enabled")
                return msg_id, 1
            if mode != "On":
                print(f"FAIL: On expected videomodehdr On, got {mode}")
                return msg_id, 1
        print(f"OK HA {option}")
    return msg_id, 0


async def _run(
    ha_host: str,
    ha_port: int,
    ha_username: str | None,
    ha_password: str | None,
    ha_access_token: str | None,
    hyperhdr_host: str,
    hyperhdr_port: int,
    admin_password: str | None,
    entity_id: str | None,
    skip_ha: bool,
) -> int:
    try:
        hyperhdr_client = await _hyperhdr_connect(
            hyperhdr_host, hyperhdr_port, admin_password
        )
    except RuntimeError as err:
        print(f"FAIL {err}")
        return 1

    try:
        print("==> HyperHDR API Off/On/Auto")
        atm, original_auto = await _run_api_steps(hyperhdr_client)
        print("PASS: HyperHDR API Off/On/Auto")

        if skip_ha:
            # Restore prior auto preference
            await _set_atm_enable(hyperhdr_client, atm, original_auto)
            await hyperhdr_client.async_set_hdr_mode(**{hyperhdr_const.KEY_HDR: 0})
            print("Skipped HA select steps (--skip-ha)")
            return 0

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
            if not entity_id:
                msg_id, entity_id = await _ha_find_entity(
                    ws, msg_id, "hyperhdr_select_hdr_tone_mapping"
                )
                if not entity_id:
                    print(
                        "FAIL: HDR tone mapping select not in entity registry "
                        "(reload/restart HA with updated custom_components)"
                    )
                    return 1
                print(f"Found entity: {entity_id}")

            print(f"==> Enabling {entity_id}")
            msg_id, enable_result = await _ha_enable_entity(ws, msg_id, entity_id)
            if not enable_result.get("success"):
                print(f"FAIL enable entity: {enable_result}")
                return 1
            # Give HA time to set up the entity after enable
            await asyncio.sleep(3)

            msg_id, state = await _ha_get_state(ws, msg_id, entity_id)
            if not state:
                print(
                    f"WARN: {entity_id} has no state yet; waiting longer "
                    "(entity may need integration reload)"
                )
                await asyncio.sleep(5)
                msg_id, state = await _ha_get_state(ws, msg_id, entity_id)
            print(f"HA entity state before test: {state.get('state')!r}")

            print("==> HA select.select_option Off/On/Auto")
            msg_id, rc = await _run_ha_steps(
                ws, msg_id, entity_id, hyperhdr_client
            )
            if rc != 0:
                return rc

        # Leave Auto enabled if that was original, else Off
        atm = await _get_atm(hyperhdr_client)
        await _set_atm_enable(hyperhdr_client, atm, original_auto)
        if not original_auto:
            await hyperhdr_client.async_set_hdr_mode(**{hyperhdr_const.KEY_HDR: 0})
        print("PASS: HA HDR Tone Mapping Mode select E2E")
        return 0
    except RuntimeError as err:
        print(f"FAIL {err}")
        return 1
    finally:
        await hyperhdr_client.async_client_disconnect()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ha-host", default="127.0.0.1")
    parser.add_argument("--ha-port", type=int, default=8123)
    parser.add_argument("--ha-username", default=None)
    parser.add_argument("--ha-password", default=None)
    parser.add_argument("--ha-access-token", default=None)
    parser.add_argument("--hyperhdr-host", default="10.12.0.12")
    parser.add_argument("--hyperhdr-port", type=int, default=19444)
    parser.add_argument("--admin-password", default=None)
    parser.add_argument(
        "--entity-id",
        default=None,
        help="HDR mode select entity_id (auto-discovered if omitted)",
    )
    parser.add_argument(
        "--skip-ha",
        action="store_true",
        help="Only run HyperHDR API checks (no Home Assistant websocket)",
    )
    args = parser.parse_args()
    return asyncio.run(
        _run(
            args.ha_host,
            args.ha_port,
            args.ha_username,
            args.ha_password,
            args.ha_access_token,
            args.hyperhdr_host,
            args.hyperhdr_port,
            args.admin_password,
            args.entity_id,
            args.skip_ha,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
