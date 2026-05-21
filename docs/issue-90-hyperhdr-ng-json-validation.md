# Issue #90: HyperHDR JSON validation (`calculate-colors`)

**GitHub:** [Shaffer-Softworks/hyperhdr-ha#90](https://github.com/Shaffer-Softworks/hyperhdr-ha/issues/90)

**Reported:** Integration v0.10.5, HyperHDR v21.0.0.0, host `hyperhdr.brunt.ca`

## Symptoms

### Home Assistant

```
WARNING [hyperhdr.client] Failed HyperHDR (hyperhdr.brunt.ca:19444) command:
{'command': '', 'error': 'Errors during message validation, please consult the HyperHDR Log.',
 'success': False, 'tan': 2}
```

Often appears immediately after sensor/light setup and a successful `Connected to HyperHDR server` line.

### HyperHDR server log

```
[JSONCLIENTCONNECTION] While validating schema against json data of 'JsonRpc@...':
[root].command: Unknown enum value (allowed values are: ["color","tunnel","smoothing",...,
"current-state","ledcolors",...,"instance",...])
```

`calculate-colors` is **not** in the allowed `command` enum on HyperHDR v21 / HyperHDR.ng.

## Root cause

1. The **average color** sensor (`HyperHDRAverageColorSensor`) called `async_get_average_color()` from `hyperhdr-py-sickkick`.
2. That library method sends JSON-RPC: `{"command": "calculate-colors", "tan": N}`.
3. HyperHDR.ng validates `command` against a fixed schema; `calculate-colors` is rejected → generic validation error in HA (`command: ""` in the error reply is normal for this failure mode).
4. `tan: 2` is typically the **second** transactional request on the per-instance client after connect (first is often `serverinfo` during `async_client_connect`).

Integration entities otherwise load; the failure is noisy but non-fatal (sensor falls back to priority/stream sources).

## Fix (integration)

**File:** `custom_components/hyperhdr/sensor.py`

| Before | After |
|--------|--------|
| Always tried `async_get_average_color()` (`calculate-colors`) | Prefer `async_get_current_colors()` (`ledcolors` + `currentColors`) |
| — | Average RGB derived from `info.rgb`, `info.colors`, or `info.avgColor` |
| — | `async_get_average_color()` only if the client has **no** `async_get_current_colors` (legacy library) |

Helper: `_try_average_rgb_from_ledcolors_response()`.

## Verification

1. Deploy updated `sensor.py` (or a release that includes this change).
2. Reload the HyperHDR config entry (or restart Home Assistant).
3. Confirm HyperHDR log **no longer** shows `Unknown enum value` at startup from `192.168.1.104` (HA host).
4. Optional HA debug:

   ```yaml
   logger:
     logs:
       hyperhdr.client: debug
   ```

   Confirm `Send to server` lines use `ledcolors` / `currentColors`, not `calculate-colors`.

## Related

- Dependency: `hyperhdr-py-sickkick==0.2.0` still defines `KEY_AVERAGE_COLOR = "calculate-colors"`; integration avoids calling it on current library builds.
- Longer term: align `hyperhdr-py-sickkick` with HyperHDR.ng command names or add a native `current-state` / instance average-color wrapper upstream.

## Investigation notes (2026-04-21)

- HA connects twice: root client (`raw_connection=True`) + per-instance client.
- Light `HyperHDR full state update` debug line is unrelated to the failed RPC; it reflects `serverinfo` / subscription updates already received.
- Allowed commands on reporter’s server include `ledcolors` and `current-state` but not `calculate-colors`.
