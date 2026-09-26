[![CodeQL](https://github.com/Shaffer-Softworks/hyperhdr-ha/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/Shaffer-Softworks/hyperhdr-ha/actions/workflows/github-code-scanning/codeql)
[![Validate](https://github.com/Shaffer-Softworks/hyperhdr-ha/actions/workflows/validate.yaml/badge.svg)](https://github.com/Shaffer-Softworks/hyperhdr-ha/actions/workflows/validate.yaml)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default)

# HyperHDR custom component for Home Assistant

HyperHDR is an open source bias lighting implementation which runs on many platforms.

**This component will set up the following platforms.**

| Platform | Description |
|----------|-------------|
| `button` | Clear the configured HyperHDR priority slot (releases solid/effect control). |
| `camera` | Live LED Colors and LED Gradient camera streams via WebSocket. |
| `light` | Control HyperHDR lighting with color, brightness, and effects. |
| `sensor` | Monitor visible priority and average color information. |
| `switch` | Toggle HyperHDR components, plus Anti-flicker Filter and Continuous Output when smoothing config is available. |
| `number` | Smoothing parameters (time, update frequency, factor, stiffness, damping, Y limit) when config get/set is available. |
| `select` | Choose v22 smoothing interpolator type when config get/set is available. |

### Key Features

- **LED Colors Camera**: Live WebSocket stream of the HyperHDR imagestream output — ideal for PicCap instances or visualizing exact LED output.
- **LED Gradient Camera**: Real-time per-LED gradient visualization rendered as a JPEG image from raw RGB data.
- **Average Color Sensor**: Average RGB as hex with attributes, from `current-state`/`average-color` RPC (with LED stream and priority-color fallbacks).
- **HDR Tone Mapping**: Adjust HDR tone mapping intensity with a dedicated number entity. Supports both legacy `hdrToneMappingMode` and the newer `videomodehdr` command paths.
- **Smoothing Controls** *(conditional)*: Number and select entities for HyperHDR v22 smoothing config (`time_ms`, update frequency, factor, stiffness, damping, Y limit, interpolator type) — created when `config` getconfig succeeds. Requires **Admin Password** (or open admin auth) when HyperHDR local admin authentication is enabled.
- **Anti-flicker / Continuous Output** *(conditional)*: Config switches for `antiFlickeringFilter` and `continuousOutput`.
- **Component Switches**: Enable/disable HyperHDR components (advanced users).
- **Automatic Entity Cleanup**: Stale entities from removed features (old camera, color engine, decay, unsupported smoothing) are automatically pruned from the entity registry on integration load.
- **SSDP Auto-Discovery**: HyperHDR instances on your network are automatically discovered via SSDP/UPnP — no manual IP entry required.

![hyperhdr-logo](https://github.com/Shaffer-Softworks/hyperhdr-ha/blob/master/hyperhdr-logo.png)

## Screenshots

| Integrations | Integration detail |
|--------------|-------------------|
| [![Integrations](docs/images/integrations.png)](docs/images/integrations.png) | [![Integration detail](docs/images/integration-detail.png)](docs/images/integration-detail.png) |

| Config flow | Options |
|-------------|---------|
| [![Config flow](docs/images/config-flow.png)](docs/images/config-flow.png) | [![Options](docs/images/options-menu.png)](docs/images/options-menu.png) |

![Basement TV Strip device (v22.0.0 smoothing controls)](docs/images/basement-tv-strip-device.png)

## Installation

### Using HACS

This integration is made available through the Home Assistant Community Store default feed. Simply search for **HyperHDR** and install it directly from HACS.

Please see the [official HACS documentation](https://hacs.xyz/docs/) for information on how to install and use HACS.

Restart Home Assistant after installation. For setup and troubleshooting, see the [project wiki](https://github.com/Shaffer-Softworks/hyperhdr-ha/wiki).

### Manually (not recommended)

- Download the [latest release](https://github.com/Shaffer-Softworks/hyperhdr-ha/releases) as a **zip file** then extract it and move the `hyperhdr` folder into the `custom_components` folder in your Home Assistant installation.
- Restart Home Assistant to load the integration.

**Dependencies**: This integration requires `hyperhdr-py-sickkick==0.2.3`. When installing via HACS, the package is installed automatically. For manual installation, ensure your Home Assistant environment has this package available.

## Configuration

### Automatic Discovery (SSDP)

HyperHDR instances on your local network are automatically discovered via **SSDP** (Simple Service Discovery Protocol). When a new instance is found, a notification appears in Home Assistant's Integrations page — just click **Configure** and confirm to set it up. The host, JSON API port, and WebSocket port are all populated automatically from the discovery data.

### Manual Setup

1. In Home Assistant navigate to `Configuration` -> `Devices & Services` -> `Integrations`.
1. Click the `+ Add Integration` button.
1. Search for `HyperHDR`.
1. If you cannot find `HyperHDR` in the list then be sure to clear your browser cache and/or perform a hard-refresh of the page.
1. Enter the IP address of your HyperHDR instance.
1. *(Optional)* Enter the **WebSocket Port** (defaults to `8090`) if your HyperHDR UI/WebSocket runs on a non-standard port.
1. *(Optional)* Enter your **Admin Password** if your HyperHDR instance has Local API Authentication enabled.
1. Click the `Submit` button.

### Admin Password

If your HyperHDR instance has **Local API Authentication** enabled, the LED camera streams require authentication to receive frames. You can provide the admin password in two places:

- **During initial setup** — enter it in the optional "Admin Password" field on the connection form.
- **After setup** — go to the integration's **Options** (gear icon) and add or change the admin password there.

When configured, the LED Colors and LED Gradient camera streams authenticate using the admin password over the WebSocket connection. The same password is used to escalate privileges for **smoothing config** entities (`config` get/set) on HyperHDR builds that require admin authorization. If a token is also configured, the admin password takes priority for stream authentication (tokens do not grant the admin privileges required by `imagestream-start`). HyperHDR requires passwords to be **at least 8 characters** (the default after `hyperhdr --resetPassword` is `hyperhdr`). Leave the field blank to clear a stored password when Local API Authentication is not used.

LED camera WebSockets start only when the camera is viewed (lazy-start), so disabled/unused cameras do not open stream connections.

### Options Flow

After the integration is set up, you can adjust the following via **Options** (gear icon on the integration card):

| Option | Description |
|--------|-------------|
| **Priority** | Default priority level for light commands (0–255). |
| **Clear priority when main light turns off** | When enabled, turning off the main HyperHDR Light sends HyperHDR's `clear` command at the configured priority so USB grabber and other lower-priority sources can take over again. Disabled by default; use the **Clear Priority** button or enable this option if you want automatic clearing. |
| **Keep WLED in realtime mode when off (idle black)** | When enabled, turning off the main light keeps the LED device enabled and sends a black output instead of disabling the LED device. This prevents WLED from resuming stored presets when the light is "off". Useful for WLED backends where disabling the LED device releases WLED from realtime mode. Disabled by default. |
| **Effect Show List** | Select which effects to expose in Home Assistant. |
| **WebSocket Port** | Port for LED camera streams (default `8090`). |
| **Admin Password** | Password for LED stream authentication. |

## Advanced Features

### Entity Discovery

Entities are created automatically for each running HyperHDR instance:

- **Always created**: Light, Priority Light, Clear Priority button, Component Switches, HDR Tone Mapping, Visible Priority Sensor, Average Color Sensor, LED Colors Camera, LED Gradient Camera.
- **Conditionally created**: Smoothing Time, Smoothing Decay, Smoothing Update Frequency, and Smoothing Type entities are only created when the connected HyperHDR server exposes smoothing data in its `serverinfo` response. If the server does not expose this data, these entities are not created at all.
- **Disabled by default**: Camera entities and most number/select entities are disabled by default to avoid unnecessary overhead. Enable them in Home Assistant's entity settings if needed.

### Automatic Stale Entity Cleanup

When upgrading from older versions, the integration automatically removes stale entities from the Home Assistant entity registry:

- **Permanently removed**: The old JSON-API camera entity and the Color Engine select entity are always cleaned up.
- **Conditionally removed**: Smoothing entities (time, decay, update frequency, type) are removed for any instance whose server does not expose smoothing data.

No manual intervention is required — the cleanup runs on every integration load.

### LED Colors Camera

The **LED Colors** camera entity streams the HyperHDR imagestream over a dedicated WebSocket connection.

- **Purpose**: Designed for **PicCap** instances where the standard MJPEG stream may not work, or for visualizing the exact LED output.
- **Disabled by Default**: This entity is **disabled by default**. You must enable it in Home Assistant settings.
- **Stream Type**: Uses `HyperHDRLedColorsStream` from `hyperhdr.stream` with automatic reconnection and admin password authentication.
- **Authentication**: Requires admin password for instances with Local API Authentication enabled (token-only auth is insufficient for imagestream).

### LED Gradient Camera

The **LED Gradient** camera entity visualizes the raw per-LED color data as a gradient image.

- **Purpose**: Displays a JPEG image representing the current color of each LED, stretched to a visible height. Useful for monitoring individual LED output in real time.
- **Disabled by Default**: This entity is **disabled by default**. Enable it in Home Assistant settings if desired.
- **Stream Type**: Uses `HyperHDRLedGradientStream` from `hyperhdr.stream` with built-in RGB-to-JPEG conversion (via Pillow), automatic reconnection, and the same authentication support as the LED Colors camera.
- **Image Format**: Raw binary LED data (RGB bytes) is converted into a 1-pixel-tall JPEG image scaled to 20px height for visibility.
- **Average Color Dispatch**: This camera computes the average RGB color from each frame and dispatches it to the Average Color sensor (throttled to every 2 seconds to avoid flooding the event bus).

### Camera Troubleshooting

If the camera entities are not streaming:

1. **Verify authentication**: Ensure the admin password is configured correctly (check integration Options).
2. **Enable debug logging**:
   ```yaml
   logger:
     logs:
       custom_components.hyperhdr.camera: debug
       hyperhdr.stream: debug
   ```
3. **Check HyperHDR is streaming**: Confirm your HyperHDR instance has an active video source (USB Capture, Video Grabber, etc.).
4. **Check the WebSocket port**: The default is `8090` — make sure it matches your HyperHDR configuration.

**Viewing options in Home Assistant:**
- **Lovelace** — Add a camera card to your dashboard for live preview.
- **Developer Tools** — Use the Camera entity to view the current snapshot.
- **Mobile App** — View the live stream in the Home Assistant mobile application.
- **MJPEG Stream** — Access the raw stream at `/api/camera_proxy_stream/camera.<entity_id>`.

## Development

### Refreshing screenshots

README images live in `docs/images/` and are driven by `docs/screenshot-manifest.yaml`. With the Docker test instance running (`docker compose -f docker-compose.test.yml up -d`) and the HyperHDR entry configured:

```bash
export HA_REFRESH_TOKEN="<refresh token from HA profile Security → Long-Lived Access Tokens, or a refresh_token with client_id http://localhost:8123/>"
export HA_DEVICE_REGISTRY_PATH="$PWD/config/.storage/core.device_registry"
pip install playwright requests pyyaml
python3 -m playwright install chromium
python3 ~/.cursor/skills/ha-integration-screenshots/scripts/capture_ha_screenshots.py --repo-root .
```

Enable any disabled-by-default entities (smoothing, cameras) you want visible on the device page before capturing.

<!-- ***

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[buymecoffee]: https://www.buymeacoffee.com/ludeeus
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/custom-components/integration_blueprint.svg?style=for-the-badge
[commits]: https://github.com/custom-components/integration_blueprint/commits/master
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license]: https://github.com/custom-components/integration_blueprint/blob/main/LICENSE
[license-shield]: https://img.shields.io/github/license/custom-components/integration_blueprint.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Joakim%20Sørensen%20%40ludeeus-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/custom-components/integration_blueprint.svg?style=for-the-badge
[releases]: https://github.com/custom-components/integration_blueprint/releases
[user_profile]: https://github.com/ludeeus -->

