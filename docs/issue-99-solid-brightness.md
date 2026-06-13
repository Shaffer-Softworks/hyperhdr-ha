# Issue #99: Solid color brightness

**GitHub:** [Shaffer-Softworks/hyperhdr-ha#99](https://github.com/Shaffer-Softworks/hyperhdr-ha/issues/99) (open)

**Reported by:** @Alexey512 — Brightness slider works for HyperHDR effects but not for **Solid** color; LEDs stay visually bright when dimming a static color.

## Symptoms

1. Light entity on **Solid** with a saturated color (e.g. red).
2. Lower brightness in Home Assistant — HA state updates, but LEDs do not dim.
3. Select any **effect** and change brightness — dimming works.

## Root cause

In `HyperHDRBaseLight.async_turn_on`, brightness and color are separate paths:

- **Effects / external sources:** `async_send_set_adjustment` (`brightness` % or `luminanceGain`) affects rendered output.
- **Solid:** `async_send_set_color` sends full-intensity RGB. HyperHDR color priority does not apply the same adjustment pipeline, so the priority RGB stays visually bright.

## Fix (integration)

**File:** `custom_components/hyperhdr/light.py`

### 1. RGB scaling helpers

- `_scale_rgb_to_brightness()` — scale RGB before `async_send_set_color` for Solid.
- `_unscale_rgb_from_brightness()` — restore full-brightness RGB when syncing from HyperHDR priorities.

### 2. Optimistic state in `async_turn_on`

After resolving kwargs, before API calls:

- `ATTR_HS_COLOR` → store full-brightness `_rgb_color`.
- `ATTR_BRIGHTNESS` → store `_brightness` immediately.

Prevents brightness-only slider changes from scaling an already-dim stored color.

### 3. Solid color send path

- Compute `effective_brightness` from kwargs or `_brightness`.
- If no new `ATTR_HS_COLOR`, unscale `rgb_color` using `stored_brightness` (brightness before optimistic update).
- Send `_scale_rgb_to_brightness(base_rgb, effective_brightness)` via `async_send_set_color`.
- Still send adjustment (so switching Solid → effect keeps global brightness in sync).

### 4. Priority sync (`_update_priorities`)

For `KEY_COMPONENTID_COLOR`, HyperHDR reports scaled RGB. Unscale before storing when `origin` starts with `DEFAULT_ORIGIN` (`"Home Assistant"`). COLOR priorities use `origin` like `Home Assistant@::ffff:10.10.0.50` (not `owner`).

**Do not scale** in effect or external-source branches.

## Docker dev environment

### Container

- **Name:** `homeassistant-test`
- **Image:** `ghcr.io/home-assistant/home-assistant:stable`
- **Compose:** `docker-compose.test.yml` (repo root)
- **Mounts:**
  - `./config` → `/config` (HA config, HyperHDR config entry, entities)
  - `./custom_components` → `/config/custom_components`

### Login (test instance)

- **URL:** http://127.0.0.1:8123 (prefer `127.0.0.1` over `localhost` if auth UI sticks)
- **Credentials:** Run `scripts/docker-rebuild-ha-test.sh` to create or reset the test user (see script output).

HA 2026 WebSocket auth uses **access tokens**, not username/password on the socket.

### HyperHDR (live E2E target)

- **Host:** `10.12.0.12:19444` (from config entry in `config/.storage/core.config_entries`)
- **HA priority:** `128` (default)
- **Test light:** `light.basement_tv_strip`
- **Adjustment model on this server:** `luminanceGain` (not `brightness` %)

### Maintenance scripts

| Script | Purpose |
|--------|---------|
| `scripts/docker-rebuild-ha-test.sh` | Pull image, reset password, recreate container |
| `scripts/docker-fix-ha-ui.sh` | Clear stale refresh tokens + frontend cache (stuck authorize page) |
| `scripts/docker-test-solid-brightness.sh` | Full solid brightness E2E (copy, restart, token, test) |
| `scripts/docker_test_solid_brightness.py` | Solid #99 E2E (HA WS + HyperHDR priority RGB) |
| `scripts/docker_test_effect_brightness.py` | Effect brightness regression (adjustment + EFFECT priority) |

**Important:** Python module changes require **container restart** (or full HA restart). `reload_config_entry` is not enough for `light.py` edits.

### Stuck login UI (logo only on `/auth/authorize`)

1. Run `./scripts/docker-fix-ha-ui.sh`
2. Open http://127.0.0.1:8123 in Incognito
3. Clear site data for `localhost:8123` and `127.0.0.1:8123` if needed
4. Avoid bookmarked URLs with `auth_callback` query params

## Test results (2026-06-13)

Environment: `homeassistant-test` → HyperHDR `10.12.0.12`, entity `light.basement_tv_strip`, priority `128`.

### Solid brightness E2E (`docker_test_solid_brightness.py`)

| Step | Action | HyperHDR priority RGB |
|------|--------|-------------------------|
| 1 | Solid red, brightness 255 | `[255, 0, 0]` |
| 2 | Brightness only → 76 | `[76, 0, 0]` |
| 3 | Brightness → 255 | `[255, 0, 0]` |
| 4 | Blue, brightness 128 | `[0, 0, 128]` |

**PASS**

### Effect brightness regression (`docker_test_effect_brightness.py`)

Effect: `Rainbow swirl`

| Step | Action | Result |
|------|--------|--------|
| 1 | Effect on, brightness 255 | EFFECT active, adjustment ≈ 255 |
| 2 | Brightness → 76 | EFFECT still active, adjustment ≈ 76 |
| 3 | Brightness → 255 | EFFECT still active, adjustment ≈ 255 |

**PASS** — solid RGB scaling does not break effect dimming.

### Not automated

- Physical LED appearance (only JSON priority RGB / adjustment verified)
- `light.basement_tv_strip_priority`
- Browser UI login (API login verified; UI may need cache clear)

## Suggested commit

```
fix: scale solid color RGB by HA brightness (#99)
```

## Related

- Issue #91 clear-priority docs: `docs/issue-91-clear-priority.md`
- Upstream Hyperion HA integration has the same unscaled-solid pattern; this fix targets HyperHDR behavior per #99.
