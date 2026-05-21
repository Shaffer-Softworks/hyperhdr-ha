#!/usr/bin/env python3
"""Docker E2E test for issue #91 clear-priority behavior against a live HyperHDR server."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from hyperhdr import client, const as hyperhdr_const


def _priority_at(priorities: list[dict], level: int) -> dict | None:
    for entry in priorities or []:
        if entry.get(hyperhdr_const.KEY_PRIORITY) == level:
            return entry
    return None


async def _run(host: str, port: int, priority: int) -> int:
    async with client.HyperHDRClient(host, port) as hyperhdr_client:
        if not hyperhdr_client:
            print(f"FAIL: cannot connect to {host}:{port}")
            return 1

        await hyperhdr_client.async_sysinfo()
        initial = _priority_at(hyperhdr_client.priorities, priority)
        print(f"Initial priority {priority}: {json.dumps(initial, default=str)}")

        print(f"Step 1: set_color at priority {priority} (simulate HA solid)")
        ok = await hyperhdr_client.async_send_set_color(
            **{
                hyperhdr_const.KEY_PRIORITY: priority,
                hyperhdr_const.KEY_COLOR: [255, 0, 0],
                hyperhdr_const.KEY_ORIGIN: "HA Docker Test",
            }
        )
        if not ok:
            print("FAIL: set_color returned false")
            return 1

        await hyperhdr_client.async_sysinfo()
        after_color = _priority_at(hyperhdr_client.priorities, priority)
        if not after_color or after_color.get(hyperhdr_const.KEY_COMPONENTID) != "COLOR":
            print(f"FAIL: expected COLOR at priority {priority}, got {after_color}")
            return 1
        print(f"OK: COLOR active at priority {priority}")

        print(f"Step 2: clear priority {priority} (integration clear / turn_off)")
        ok = await hyperhdr_client.async_send_clear(
            **{hyperhdr_const.KEY_PRIORITY: priority}
        )
        if not ok:
            print("FAIL: clear returned false")
            return 1

        await hyperhdr_client.async_sysinfo()
        after_clear = _priority_at(hyperhdr_client.priorities, priority)
        if after_clear and after_clear.get("active"):
            print(f"FAIL: priority {priority} still active after clear: {after_clear}")
            return 1
        print(f"OK: priority {priority} released after clear (entry={after_clear})")

        print("Step 3: disable LEDDEVICE (main light turn_off tail)")
        ok = await hyperhdr_client.async_send_set_component(
            **{
                hyperhdr_const.KEY_COMPONENTSTATE: {
                    hyperhdr_const.KEY_COMPONENT: hyperhdr_const.KEY_COMPONENTID_LEDDEVICE,
                    hyperhdr_const.KEY_STATE: False,
                }
            }
        )
        if not ok:
            print("FAIL: LEDDEVICE off returned false")
            return 1
        print("OK: LEDDEVICE disabled")

        visible = hyperhdr_client.visible_priority
        print(f"Visible priority after clear: {json.dumps(visible, default=str)}")
        grabber = _priority_at(hyperhdr_client.priorities, 240)
        if grabber:
            print(
                f"USB grabber slot (240): active={grabber.get('active')} "
                f"visible={grabber.get('visible')}"
            )

        print("PASS: clear priority E2E against HyperHDR API")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="10.12.0.12")
    parser.add_argument("--port", type=int, default=19444)
    parser.add_argument("--priority", type=int, default=128)
    args = parser.parse_args()
    return asyncio.run(_run(args.host, args.port, args.priority))


if __name__ == "__main__":
    sys.exit(main())
