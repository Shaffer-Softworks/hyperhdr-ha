#!/usr/bin/env python3
"""Call HA services via WebSocket to verify clear-priority integration behavior."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import websockets


async def _run(host: str, port: int, username: str, password: str) -> int:
    uri = f"ws://{host}:{port}/api/websocket"
    async with websockets.connect(uri) as ws:
        await ws.recv()
        await ws.send(
            json.dumps({"type": "auth", "username": username, "password": password})
        )
        msg = json.loads(await ws.recv())
        if msg.get("type") != "auth_ok":
            print(f"FAIL auth: {msg}")
            return 1
        print("OK auth")

        msg_id = 0

        async def call_service(
            domain: str, service: str, entity_id: str, service_data: dict | None = None
        ) -> dict:
            nonlocal msg_id
            msg_id += 1
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
            return json.loads(await ws.recv())

        r = await call_service(
            "light",
            "turn_on",
            "light.basement_tv_strip",
            {"rgb_color": [255, 0, 0], "effect": "Solid"},
        )
        print(f"turn_on: success={r.get('success')}")
        await asyncio.sleep(2)

        r = await call_service("light", "turn_off", "light.basement_tv_strip")
        print(f"turn_off: success={r.get('success')}")
        await asyncio.sleep(2)

        r = await call_service(
            "light",
            "turn_on",
            "light.basement_tv_strip",
            {"rgb_color": [0, 0, 255], "effect": "Solid"},
        )
        print(f"turn_on (blue): success={r.get('success')}")
        await asyncio.sleep(1)

        r = await call_service(
            "button", "press", "button.basement_tv_strip_clear_priority"
        )
        print(f"button.press: success={r.get('success')}")

    print("PASS: HA service calls completed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--username", default="test")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    return asyncio.run(_run(args.host, args.port, args.username, args.password))


if __name__ == "__main__":
    sys.exit(main())
