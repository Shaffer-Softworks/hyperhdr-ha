<!-- [![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]][license]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

_Component to integrate with [integration_blueprint][integration_blueprint]._ -->

# HyperHDR custom component for Home Assistant

HyperHDR is an open source bias lighting implementation which runs on many platforms.

**This component will set up the following platforms.**

| Platform | Description |
|----------|-------------|
| `camera` | Live video stream from HyperHDR (when available from video/USB capture). |
| `light` | Control HyperHDR lighting with color, brightness, and effects. |
| `sensor` | Monitor visible priority and average color information. |
| `switch` | Toggle HyperHDR components (smoothing, HDR tone mapping, blackborder detection, etc.). |
| `number` | Adjust smoothing parameters (time, decay, update frequency) and HDR tone mapping intensity. |
| `select` | Choose smoothing type (linear, exponential, inertia, hybrid, yuv) and color engine mode (infinite, linear, hybrid). |

### Key Features

- **Average Color Sensor**: Real-time average color display with hex value and RGB attributes.
- **Smoothing Controls**: Fine-tune smoothing behavior via number entities for time, decay, and update frequency.
- **HDR Tone Mapping**: Adjust HDR tone mapping intensity with a dedicated number entity.
- **Color Engine Selection**: Switch between infinite, linear, and hybrid color engine modes via select entity.
- **Smoothing Type Selection**: Choose from multiple smoothing interpolation algorithms.
- **Service Integration**: Use the `hyperhdr.set_color_engine` service for advanced color engine control via automations.
- **Component Switches**: Enable/disable HyperHDR components (advanced users).
- **Live Camera Stream**: View real-time video from USB capture or video grabber sources.

![hyperhdr-logo](https://github.com/mjoshd/hyperhdr-ha/blob/master/hyperhdr-logo.png)

## Installation

### Using HACS

1. Add <https://github.com/mjoshd/hyperhdr-ha> to your [HACS](https://hacs.xyz/) custom repositories.
1. Choose `Integration` from the category selection.
1. Click install.
1. Return to the Integrations page within HACS then click the `+ Explore & download repositories` button.
1. Search for `HyperHDR`, select it, then click `Download this repository with HACS`.
1. Restart Home Assistant to load the integration.
1. Visit the Wiki for information regarding: 
    - [Initial Setup](https://github.com/mjoshd/hyperhdr-ha/wiki#initial-setup)
    - [Post-setup Advice](https://github.com/mjoshd/hyperhdr-ha/wiki#post-setup-advice)
    - [Debug Logging](https://github.com/mjoshd/hyperhdr-ha/wiki#debug-logging)

### Manually (not recommended)

- Download the [latest release](https://github.com/mjoshd/hyperhdr-ha/releases) as a **zip file** then extract it and move the `hyperhdr` folder into the `custom_components` folder in your Home Assistant installation.
- Restart Home Assistant to load the integration.

**Dependencies**: This integration requires `hyperhdr-py-sickkick==0.2.0`. When installing via HACS, the package is installed automatically. For manual installation, ensure your Home Assistant environment has this package available.

## Configuration

1. In Home Assistant navigate to `Configuration` -> `Devices & Services` -> `Integrations`.
1. Click the `+ Add Integration` button.
1. Search for `HyperHDR`.
1. If you cannot find `HyperHDR` in the list then be sure to clear your browser cache and/or perform a hard-refresh of the page.
1. Enter the IP address of your HyperHDR instance.
1. *(Optional)* Enter your **Admin Password** if your HyperHDR instance has Local API Authentication enabled.
1. Click the `Submit` button.

### Admin Password

If your HyperHDR instance has **Local API Authentication** enabled (`adminRequired: true`), the LED camera streams require authentication to receive frames. You can provide the admin password in two places:

- **During initial setup** — enter it in the optional "Admin Password" field on the connection form.
- **After setup** — go to the integration's **Options** (gear icon) and add or change the admin password there.

When configured, the LED Colors and LED Gradient camera streams will first attempt token-based authentication. If that fails (or no token is available), they automatically fall back to admin password login over the WebSocket connection. If your HyperHDR instance does not require authentication, you can leave this field blank.

## Advanced Features

### Using the Color Engine Service

For advanced automation and control, you can use the `hyperhdr.set_color_engine` service to send custom color engine payloads:

```yaml
service: hyperhdr.set_color_engine
data:
  instance: 0
  data:
    colorEngine:
      type: infinite
```

### Entity Discovery

Most entities are created automatically for each HyperHDR instance. Some entities (like smoothing and HDR controls) are disabled by default for advanced users. Enable them in Home Assistant's entity settings if needed.

### Camera Live Preview

The camera entity is **disabled by default** due to performance considerations. To enable live camera preview:

1. Go to **Settings** → **Devices & Services** → **Entities**
2. Search for `HyperHDR` camera entity
3. Click the entity to open its details
4. Click the toggle switch to **enable** the camera
5. The live preview will now appear in the Lovelace UI

**Requirements for live preview:**
- HyperHDR instance must have a **video/USB capture source** active (not color priority)
- The camera will only display frames when an image stream is available
- Stream quality depends on the active HyperHDR priority source

**Viewing options in Home Assistant:**
- **Lovelace** - Add a camera card to your dashboard for live preview
- **Developer Tools** - Use the Camera entity to view current snapshot
- **Mobile App** - View live stream in Home Assistant mobile application
- **MJPEG Stream** - Access raw stream at `/api/camera_proxy_stream/camera.hyperhdr_<instance>`

**Troubleshooting - Getting only screenshots instead of live video:**

If you're seeing only still images instead of a continuous live stream:

1. **Enable debug logging** to diagnose the issue:
   - Go to **Developer Tools** → **Logs**
   - Add this to your Home Assistant `configuration.yaml`:
     ```yaml
     logger:
       logs:
         custom_components.hyperhdr.camera: debug
     ```
   - Restart Home Assistant and check the logs

2. **Verify HyperHDR is streaming images**:
   - Check that your HyperHDR instance has an **active video source** (USB Capture, Video Grabber, etc.)
   - Color-only priorities will not produce image streams
   - Go to HyperHDR web UI and confirm you can see live video there

3. **Check Lovelace camera card configuration**:
   - Make sure you're using the **Camera** card type (not picture entity)
   - The card should automatically use MJPEG streaming
   - Try refreshing your browser or clearing cache if it still shows static images

4. **Network/Performance issues**:
   - Live streaming may be slow on weak networks
   - Check Home Assistant system logs for any errors
   - Try accessing the raw stream: `http://<home-assistant-ip>:8123/api/camera_proxy_stream/camera.hyperhdr_<instance_number>`

### Camera Stream Notes

The camera entity provides a live video stream when available:
- **Video/USB Capture sources** will stream live images
- **Color priorities** do not stream (no image data available)
- Stream behavior depends on active HyperHDR priority source
- **Performance**: The camera is disabled by default to avoid unnecessary stream overhead

### LED Colors Camera

A second camera entity named **"LED Colors"** is also created. This entity streams the HyperHDR imagestream over a dedicated WebSocket connection.

- **Purpose**: Designed for **PicCap** instances where the standard MJPEG stream may not work, or for visualizing the exact LED output.
- **Disabled by Default**: Like the standard camera, this entity is **disabled by default**. You must enable it in Home Assistant settings.
- **Stream Type**: Uses `HyperHDRLedColorsStream` from `hyperhdr.stream` with automatic reconnection, token authentication, and admin password fallback.
- **Authentication**: Supports token-based and admin password authentication for instances with Local API Authentication enabled.

### LED Gradient Camera

A third camera entity named **"LED Gradient"** visualizes the raw per-LED color data as a gradient image.

- **Purpose**: Displays a JPEG image representing the current color of each LED, stretched to a visible height. Useful for monitoring individual LED output in real time.
- **Disabled by Default**: This entity is **disabled by default**. Enable it in Home Assistant settings if desired.
- **Stream Type**: Uses `HyperHDRLedGradientStream` from `hyperhdr.stream` with built-in RGB-to-JPEG conversion (via Pillow), automatic reconnection, and the same authentication support as the LED Colors camera.
- **Image Format**: Raw binary LED data (RGB bytes) is converted into a 1-pixel-tall JPEG image scaled to 20px height for visibility.

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


