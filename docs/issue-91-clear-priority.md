# Issue #91: Clear Priority for solid/effect light

**GitHub:** [Shaffer-Softworks/hyperhdr-ha#91](https://github.com/Shaffer-Softworks/hyperhdr-ha/issues/91) (closed)  
**PR:** [#92](https://github.com/Shaffer-Softworks/hyperhdr-ha/pull/92) (merged `0971dd0`, 2026-05-21)

**Reported by:** @Mofx-01 — USB grabber blocked after using solid color or effect via the main HyperHDR Light; priority slot at HA’s configured level (default 128) stayed active until manually cleared in the HyperHDR web UI JSON API.

## Symptoms

1. USB grabber (or other lower-priority source) is active.
2. User sets **Solid** color or an **effect** on the main **HyperHDR Light**.
3. User turns off the light or tries to return to USB capture — grabber does not resume because the HA priority entry remains active.
4. Selecting **USB Capture** from the light’s effect list *did* clear first; turning the light off or toggling component switches did not.

## Root cause

`HyperHDRLight.async_turn_off` only disabled `LEDDEVICE`. It never sent HyperHDR `command: "clear"` with the configured `priority`.

`HyperHDRPriorityLight` already cleared on turn-off (clear + black). Effect and external-source `turn_on` paths already called `async_send_clear` before applying.

## Fix (integration)

### 1. Clear Priority button (`button` platform)

- **File:** `custom_components/hyperhdr/button.py`
- **Entity:** `button.<instance>_clear_priority` (translation: **Clear Priority**)
- **Action:** `async_send_clear(**{priority: <CONF_PRIORITY>})` — same as HyperHDR web UI JSON API
- **Default:** entity enabled

### 2. Optional auto-clear on main light turn-off

- **Option:** `clear_priority_on_turn_off` in config entry options (`config_flow.py`)
- **Constant:** `CONF_CLEAR_PRIORITY_ON_TURN_OFF`, `DEFAULT_CLEAR_PRIORITY_ON_TURN_OFF = False`
- **Behavior:** When enabled, `HyperHDRLight.async_turn_off` calls clear at configured priority, then disables `LEDDEVICE` (clear only — no black placeholder, unlike Priority Light off)
- **Default:** **off** — avoids surprising existing users; opt-in for issue #91 workflow

### 3. Shared helper

- **File:** `custom_components/hyperhdr/light.py`
- **Method:** `HyperHDRBaseLight._async_clear_configured_priority()`
- Used by main light turn-off (when option on), effect/external paths, Priority Light turn-off, and conceptually mirrors button behavior

### 4. Platform registration

- `Platform.BUTTON` added to `PLATFORMS` in `__init__.py`
- Types/translations/icons: `const.py`, `en.json`, `icons.json`
- User docs: `README.md`, `wiki/Home.md`

## Configuration

| Option | Key | Default | Range / type |
|--------|-----|---------|----------------|
| HyperHDR priority for colors/effects | `priority` | `128` | 0–255 (existing) |
| Clear priority when main light turns off | `clear_priority_on_turn_off` | `false` | boolean |

## Verification (2026-05-20)

Tested with Docker container `homeassistant-test` (bind-mounts repo `custom_components` + `config`) against live HyperHDR `10.12.0.12:19444`.

### HyperHDR API E2E

Script: `scripts/docker_test_clear_priority.py`  
Flow: `set_color` @ 128 → `clear` @ 128 → `LEDDEVICE` off → PASS

### Home Assistant services (WebSocket / REST via login flow)

Observed in `hyperhdr.client` debug logs after `light.turn_off`:

```json
{"command": "clear", "priority": 128}
{"command": "componentstate", "componentstate": {"component": "LEDDEVICE", "state": false}}
```

After `button.press` on `button.basement_tv_strip_clear_priority`:

```json
{"command": "clear", "priority": 128}
```

### Helper scripts

| Script | Purpose |
|--------|---------|
| `scripts/docker-test-clear-priority.sh` | Start `homeassistant-test`, run API E2E |
| `scripts/docker_test_clear_priority.py` | Direct HyperHDR JSON-RPC test |
| `scripts/ha_ws_test_clear_priority.py` | HA service calls via WebSocket (needs password arg; HA 2026.2 uses login flow, not password grant on `/auth/token`) |

## Docker dev setup (this machine)

```text
Container: homeassistant-test
Image:     ghcr.io/home-assistant/home-assistant:stable
Mounts:    hyperhdr-ha/config → /config
           hyperhdr-ha/custom_components → /config/custom_components
Port:      8123 → localhost
```

## Out of scope (follow-ups)

- Clear when enabling **USB Capture** component switch (user never turns off light)
- `hyperhdr.clear_priority` HA service (button + automations sufficient)

## Related

- HyperHDR JSON API: [clear](https://docs.hyperhdr-project.org/en/json/Control.html#clear)
- Library: `hyperhdr-py-sickkick` → `HyperHDRClient.async_send_clear`
