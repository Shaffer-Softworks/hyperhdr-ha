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

![hyperhdr-logo](https://github.com/sickkick/hyperhdr-ha/blob/master/hyperhdr-logo.png)

## Installation

### Using HACS

1. Add <https://github.com/sickkick/hyperhdr-ha> to your [HACS](https://hacs.xyz/) custom repositories.
1. Choose `Integration` from the category selection.
1. Click install.
1. Return to the Integrations page within HACS then click the `+ Explore & download repositories` button.
1. Search for `HyperHDR`, select it, then click `Download this repository with HACS`.
1. Restart Home Assistant to load the integration.
1. Visit the Wiki for information regarding: 
    - [Initial Setup](https://github.com/sickkick/hyperhdr-ha/wiki#initial-setup)
    - [Post-setup Advice](https://github.com/sickkick/hyperhdr-ha/wiki#post-setup-advice)
    - [Debug Logging](https://github.com/sickkick/hyperhdr-ha/wiki#debug-logging)

### Manually (not recommended)

- Download the [latest release](https://github.com/sickkick/hyperhdr-ha/releases) as a **zip file** then extract it and move the `hyperhdr` folder into the `custom_components` folder in your Home Assistant installation.
- Restart Home Assistant to load the integration.

**Dependencies**: This integration requires `hyperhdr-py-sickkick==0.1.0`. When installing via HACS, the package is installed automatically. For manual installation, ensure your Home Assistant environment has this package available.

## Configuration

1. In Home Assistant navigate to `Configuration` -> `Devices & Services` -> `Integrations`.
1. Click the `+ Add Integration` button.
1. Search for `HyperHDR`.
1. If you cannot find `HyperHDR` in the list then be sure to clear your browser cache and/or perform a hard-refresh of the page.
1. Enter the IP address of your HyperHDR instance.
1. Click the `Submit` button.

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

### Camera Stream Notes

The camera entity provides a live video stream when available:
- **Video/USB Capture sources** will stream live images
- **Color priorities** do not stream (no image data available)
- Stream behavior depends on active HyperHDR priority source

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


