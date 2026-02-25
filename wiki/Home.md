# Welcome to the hyperhdr-ha wiki!

HyperHDR is an open source bias lighting implementation which runs on many platforms. This custom component integrates HyperHDR with Home Assistant, providing control over lighting, effects, component switches, camera streams, and more.

---

## Table of Contents

**Initial Setup**
- Authentication
- Manual Setup
- Automatic Discovery (SSDP)

**Platforms & Entities**
- Select
- Number
- Sensor
- Camera
- Switch
- Light

**Advanced Features**
- Camera Troubleshooting
- Automatic Entity Cleanup
- Multi-Instance Support

---

## Installation

### Using HACS

1. Add [https://github.com/Shaffer-Softworks/hyperhdr-ha](https://github.com/Shaffer-Softworks/hyperhdr-ha) to your [HACS](https://hacs.xyz/) custom repositories.
2. Choose **Integration** from the category selection.
3. Click install.
4. Return to the Integrations page within HACS then click the **+ Explore & download repositories** button.
5. Search for **HyperHDR**, select it, then click **Download this repository with HACS**.
6. Restart Home Assistant to load the integration.
7. Visit the Wiki for: [Initial Setup](#initial-setup), [Post-setup Advice](#post-setup-advice), [Debug Logging](#debug-logging).

### Manual Installation (not recommended)

- Download the [latest release](https://github.com/Shaffer-Softworks/hyperhdr-ha/releases) as a zip file, extract it, and move the `hyperhdr` folder into the `custom_components` folder in your Home Assistant installation.
- Restart Home Assistant to load the integration.

**Dependencies:** This integration requires `hyperhdr-py-sickkick==0.2.0`. When installing via HACS, the package is installed automatically. For manual installation, ensure your Home Assistant environment has this package available.

---

## Initial Setup

### Automatic Discovery (SSDP)

HyperHDR instances on your local network are automatically discovered via SSDP (Simple Service Discovery Protocol). When a new instance is found, a notification appears in Home Assistant's Integrations page — just click Configure and confirm to set it up. The host, JSON API port, and WebSocket port are all populated automatically from the discovery data.

### Manual Setup

1. In Home Assistant go to **Configuration** → **Devices & Services** → **Integrations**.
2. Click the **+ Add Integration** button.
3. Search for **HyperHDR**.
4. If you cannot find **HyperHDR** in the list, clear your browser cache and/or perform a hard-refresh of the page.
5. Enter the host (and optional WebSocket port and admin password), then click **Submit**.

### Authentication

If your HyperHDR instance has Local API Authentication enabled, the integration will guide you through a token-based authentication flow:

- **Option 1:** Provide an existing authentication token.
- **Option 2:** Create a new token automatically — the integration generates a random auth ID, opens the HyperHDR UI for approval, and validates the token once approved.
- Click the **Submit** button.

Additionally, the LED camera streams require the admin password for authentication (token-only auth is insufficient for the `imagestream-start` command). You can provide the admin password during initial setup or add/change it later via the integration's **Options**.

---

## Options Flow

After the integration is set up, you can adjust settings via the **Options** gear icon on the integration card.

| Option | Description | Default |
|--------|-------------|---------|
| Priority | Default priority level for light commands (0–255). | `128` |
| Effect Show List | Select which HyperHDR effects to expose in Home Assistant. New effects added to HyperHDR will appear by default. | All effects shown |
| WebSocket Port | Port for LED camera streams. | `8090` |
| Admin Password | Password for LED stream authentication (required if Local API Authentication is enabled in HyperHDR). | (empty) |

---

## Platforms & Entities

This integration creates the following platforms:

| Platform | Description |
|----------|-------------|
| `camera` | Live LED Colors and LED Gradient camera streams via WebSocket. |
| `light` | Control HyperHDR lighting with color, brightness, and effects. |
| `sensor` | Monitor visible priority and average color information. |
| `switch` | Toggle HyperHDR components (smoothing, HDR tone mapping, blackbar detection, etc.). |
| `number` | Adjust HDR tone mapping intensity. Smoothing parameters (time, decay, update frequency) when the server exposes smoothing data. |
| `select` | Choose smoothing type (linear, exponential, inertia, hybrid-rgb, yuv) when the server exposes smoothing data. |

### Light

Two light entities are created for each HyperHDR instance:

- **HyperHDR Priority Light** (disabled by default) — Controls only the configured priority level (default 128). Does not support external effects. Useful for advanced priority-based control.
- **HyperHDR Light** (enabled by default) — Controls the LED device on/off state and displays the currently visible priority. Supports color, brightness, and effect selection (including external source effects like Video Grabber and USB Capture).

Both entities expose HyperHDR effects in the effect list. The "Solid" effect is always available for setting solid colors.

### Switch

Nine component switches are created (all disabled by default), intended for advanced users:

| Switch | Description |
|--------|-------------|
| All | Master toggle for all components |
| Smoothing | Toggle LED smoothing |
| Blackbar Detection | Toggle blackbar detection |
| Forwarder | Toggle priority forwarder |
| Boblight Server | Toggle Boblight server |
| Platform Capture | Toggle platform screen capture |
| LED Device | Toggle the LED device output |
| USB Capture | Toggle USB video capture |
| HDR Tone Mapping | Toggle HDR tone mapping processing |

### Camera

Two camera entities are created (both disabled by default):

#### LED Colors Camera

Streams the HyperHDR imagestream output over a dedicated WebSocket connection.

- **Authentication:** Requires admin password when Local API Authentication is enabled.
- **Stream Type:** Uses `HyperHDRLedColorsStream` with automatic reconnection.
- **Purpose:** Designed for PicCap instances where the standard MJPEG stream may not work, or for visualizing the exact LED output.

#### LED Gradient Camera

Visualizes the raw per-LED color data as a gradient image.

- **Average Color:** This camera computes the average RGB color from each frame and dispatches it to the Average Color sensor (throttled to every 2 seconds).
- **Image Format:** Raw binary LED data (RGB bytes) is converted into a 1-pixel-tall JPEG image scaled to 20px height for visibility.
- **Purpose:** Displays a JPEG image representing the current color of each LED, stretched to a visible height. Useful for monitoring individual LED output in real time.

### Sensor

Two sensor entities are created:

#### Visible Priority Sensor

Shows the currently active (visible) priority with detailed attributes: Color, Owner, Priority level, Origin, Component ID.

#### Average Color Sensor

Displays the average RGB color as a hex value with RGB array attributes. Data sources (in priority order):

1. Visible priority COLOR component — falls back to the color of the currently visible priority.
2. Server-side `calculate-colors` — uses the HyperHDR v20+ server API when available.
3. LED gradient stream — real-time data from the LED Gradient camera (throttled to 2-second intervals).

### Number

Up to four number entities are created:

| Entity | Range | Step | Condition |
|--------|-------|------|-----------|
| HDR Tone Mapping | 0.0–2.0 | 0.1 | Always created (disabled by default) |
| Smoothing Time | 0–1000 ms | 1 | Only if server exposes smoothing data |
| Smoothing Decay | 0.0–1.0 | 0.01 | Only if server exposes smoothing data |
| Smoothing Update Frequency | 0–1000 Hz | 1 | Only if server exposes smoothing data |

### Select

One select entity is conditionally created:

- **Smoothing Type** (disabled by default) — Options: `linear`, `exponential`, `inertia`, `hybrid-rgb`, `yuv`. Only created when the server exposes smoothing data.

---

## Advanced Features

### Multi-Instance Support

The integration supports multiple HyperHDR instances per server. Entities are created dynamically for each running instance and are automatically added or removed as instances start and stop. All entities for a given instance are grouped under a single device in Home Assistant.

### Automatic Entity Cleanup

When upgrading from older versions, the integration automatically removes stale entities from the Home Assistant entity registry:

- **Permanently removed:** The old JSON-API camera entity and the Color Engine select entity (both removed in v0.1.5) are always cleaned up.
- **Conditionally removed:** Smoothing entities (time, decay, update frequency, type) are removed for any instance whose server does not expose smoothing data.

No manual intervention is required — the cleanup runs on every integration load.

### Camera Troubleshooting

If the camera entities are not streaming:

1. **Enable the entity:** Both camera entities are disabled by default. Enable them in Home Assistant's entity settings first.
2. **Check HyperHDR is streaming:** Confirm your HyperHDR instance has an active video source (USB Capture, Video Grabber, etc.).
3. **Check the WebSocket port:** The default is `8090` — make sure it matches your HyperHDR configuration.
4. **Verify authentication:** Ensure the admin password is configured correctly (check integration **Options**).
5. **Enable debug logging** (see [Debug Logging](#debug-logging) below for camera-specific logging).

```yaml
logger:
  logs:
    custom_components.hyperhdr.camera: debug
    hyperhdr.stream: debug
```

Viewing options in Home Assistant: **Lovelace** — Add a camera card to your dashboard. **Developer Tools** — Use the Camera entity to view the current snapshot. **Mobile App** — View the live stream in the Home Assistant mobile application. **MJPEG Stream** — Access the raw stream at `/api/camera_proxy_stream/camera.<entity_id>`.

---

## Post-setup Advice

The best settings for an individual's HyperHDR setup are subjective and will vary greatly; my recommendations:

1. Go into the HyperHDR web UI → **Image Processing** → **Color Calibration**.
2. Un-check **Colored backlight**.
3. Un-check **Classic HyperHDR calibration**.
4. Click **Save settings**.

---

## Debug Logging

Add the following to the [logger](https://www.home-assistant.io/components/logger/) section of your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.hyperhdr: debug
```

For more targeted debugging, you can enable logging for specific modules:

```yaml
logger:
  default: warning
  logs:
    custom_components.hyperhdr: debug           # all integration logs
    custom_components.hyperhdr.camera: debug    # camera-specific logs
    custom_components.hyperhdr.light: debug    # light-specific logs
    hyperhdr.stream: debug                      # WebSocket stream library logs
```
