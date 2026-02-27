[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]][license]

[![hacs][hacsbadge]][hacs]

# HyperHDR custom component for Home Assistant

HyperHDR is an open source bias lighting implementation which runs on many platforms.

**This component will set up the following platforms.**

| Platform | Description |
|----------|-------------|
| `camera` | Live LED Colors and LED Gradient camera streams via WebSocket. |
| `light` | Control HyperHDR lighting with color, brightness, and effects. |
| `sensor` | Monitor visible priority and average color information. |
| `switch` | Toggle HyperHDR components (smoothing, HDR tone mapping, blackborder detection, etc.). |
| `number` | Adjust HDR tone mapping intensity. Smoothing parameters (time, decay, update frequency) are available when the server exposes smoothing data. |
| `select` | Choose smoothing type (linear, exponential, inertia, hybrid, yuv) when the server exposes smoothing data. |

### Key Features

- **LED Colors Camera**: Live WebSocket stream of the HyperHDR imagestream output — ideal for PicCap instances or visualizing exact LED output.
- **LED Gradient Camera**: Real-time per-LED gradient visualization rendered as a JPEG image from raw RGB data.
- **Average Color Sensor**: Real-time average color display with hex value and RGB attributes (computed from LED stream data with throttled updates).
- **HDR Tone Mapping**: Adjust HDR tone mapping intensity with a dedicated number entity. Supports both legacy `hdrToneMappingMode` and the newer `videomodehdr` command paths.
- **Smoothing Controls** *(conditional)*: Number entities for time, decay, and update frequency — only created when the connected HyperHDR server exposes smoothing data.
- **Smoothing Type Selection** *(conditional)*: Choose from multiple smoothing interpolation algorithms — only created when smoothing data is available.
- **Component Switches**: Enable/disable HyperHDR components (advanced users).
- **Automatic Entity Cleanup**: Stale entities from removed features (old camera, color engine, unsupported smoothing) are automatically pruned from the entity registry on integration load.
- **SSDP Auto-Discovery**: HyperHDR instances on your network are automatically discovered via SSDP/UPnP — no manual IP entry required.

![hyperhdr-logo](https://github.com/Shaffer-Softworks/hyperhdr-ha/blob/master/hyperhdr-logo.png)

## Installation

### Using HACS

1. Add <https://github.com/Shaffer-Softworks/hyperhdr-ha> to your [HACS](https://hacs.xyz/) custom repositories.
1. Choose `Integration` from the category selection.
1. Click install.
1. Return to the Integrations page within HACS then click the `+ Explore & download repositories` button.
1. Search for `HyperHDR`, select it, then click `Download this repository with HACS`.
1. Restart Home Assistant to load the integration.
1. Visit the Wiki for information regarding: 
    - [Initial Setup](https://github.com/Shaffer-Softworks/hyperhdr-ha/wiki#initial-setup)
    - [Post-setup Advice](https://github.com/Shaffer-Softworks/hyperhdr-ha/wiki#post-setup-advice)
    - [Debug Logging](https://github.com/Shaffer-Softworks/hyperhdr-ha/wiki#debug-logging)

### Manually (not recommended)

- Download the [latest release](https://github.com/Shaffer-Softworks/hyperhdr-ha/releases) as a **zip file** then extract it and move the `hyperhdr` folder into the `custom_components` folder in your Home Assistant installation.
- Restart Home Assistant to load the integration.

**Dependencies**: This integration requires `hyperhdr-py-sickkick==0.2.0`. When installing via HACS, the package is installed automatically. For manual installation, ensure your Home Assistant environment has this package available.

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

When configured, the LED Colors and LED Gradient camera streams authenticate using the admin password over the WebSocket connection. If a token is also configured, the admin password takes priority for stream authentication (tokens do not grant the admin privileges required by `imagestream-start`). If your HyperHDR instance does not require authentication, you can leave this field blank.

### Options Flow

After the integration is set up, you can adjust the following via **Options** (gear icon on the integration card):

| Option | Description |
|--------|-------------|
| **Priority** | Default priority level for light commands (0–255). |
| **Effect Show List** | Select which effects to expose in Home Assistant. |
| **WebSocket Port** | Port for LED camera streams (default `8090`). |
| **Admin Password** | Password for LED stream authentication. |

## Advanced Features

### Entity Discovery

Entities are created automatically for each running HyperHDR instance:

- **Always created**: Light, Priority Light, Component Switches, HDR Tone Mapping, Visible Priority Sensor, Average Color Sensor, LED Colors Camera, LED Gradient Camera.
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

