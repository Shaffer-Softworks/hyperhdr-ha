<!-- {% if not installed %} -->

## Installation

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

## Configuration

HyperHDR instances are automatically discovered via **SSDP**. When found, a notification appears in Integrations — click **Configure** to confirm. You can also set up manually:

1. In Home Assistant navigate to `Configuration` -> `Devices & Services` -> `Integrations`.
1. Click the `+ Add Integration` button.
1. Search for `HyperHDR`.
1. If you cannot find `HyperHDR` in the list then be sure to clear your browser cache and/or perform a hard-refresh of the page.
1. Enter the IP address of your HyperHDR instance.
1. *(Optional)* Enter the **WebSocket Port** (defaults to `8090`) for LED camera streams.
1. *(Optional)* Enter your **Admin Password** if your HyperHDR instance has Local API Authentication enabled.
1. Click the `Submit` button.

<!-- {% endif %} -->

<!-- {% if installed %} -->
<!-- {% if installed %} -->
# Integration v0.1.6

**Entity Cleanup & Config Entry Migration:**
- Bumped config entry VERSION to 2 — existing entries are automatically migrated
- Added automatic **stale entity cleanup** on every integration load:
  - Permanently removed entities (old JSON-API camera, Color Engine select) are pruned from the entity registry
  - Smoothing entities (time, decay, update frequency, type) are pruned per-instance when the server does not expose smoothing data
- No manual cleanup required when upgrading — stale entities are removed automatically

# Integration v0.1.5

**Codebase Cleanup & UI Refinements:**
- Removed the old **JSON-API camera** (`HyperHDRCamera`) — only LED Colors and LED Gradient cameras remain
- Removed the **Color Engine** select entity and `hyperhdr.set_color_engine` service (not supported by the connected server)
- Smoothing entities (number and select) are now **conditionally created** only when the HyperHDR server exposes smoothing data
- Cleaned up **switch entity names** — removed redundant "Component" prefix from all translations
- Added **average color throttling** (2-second interval) and deduplication to reduce event bus and recorder load
- Camera entities now correctly report **"streaming"** state (instead of "idle") when receiving frames
- Added **initial state population** for all entities on load (visible priority, average color, switches, smoothing, HDR)
- Updated **Options flow** to allow changing the WebSocket port after setup
- Bumped manifest version to `0.1.5`

# Integration v0.1.4

**Stream API & Admin Password Authentication:**
- Refactored LED Colors and LED Gradient cameras to use the new `HyperHDRLedColorsStream` and `HyperHDRLedGradientStream` classes from `hyperhdr.stream`, replacing inline WebSocket code with the library's streaming layer
- Added **admin password** as an optional configuration field (available during setup and in the Options flow) for authenticating LED camera streams when HyperHDR has Local API Authentication enabled
- Stream authentication now tries token auth first, then automatically falls back to admin password login
- Updated HDR Tone Mapping number entity to support the new `videomodehdr` command path alongside the legacy `hdrToneMappingMode`
- Bumped `hyperhdr-py-sickkick` dependency to `0.2.0`

# Integration v0.0.9

**Major Features Added:**
- **Average Color Sensor**: Real-time color monitoring with hex display and RGB attributes
- **Smoothing Controls**: Number entities for adjusting smoothing time, decay, and update frequency
- **HDR Tone Mapping**: Dedicated number entity for HDR intensity adjustment
- **Camera Integration**: Enabled live video streaming from USB capture and video grabber sources
- **Smoothing Type Selection**: Choose from linear, exponential, inertia, hybrid-rgb, and yuv smoothing types

**Dependency Update:**
- Updated to use `hyperhdr-py-sickkick==0.1.0` with enhanced API support for average color and smoothing controls
- All new platforms (sensor, number, select, camera) are included

**Improvements:**
- Enhanced sensor platform with improved entity lifecycle management
- Added entity category support for advanced users (most new controls disabled by default)
- Improved documentation with feature descriptions and usage examples

# Integration v0.0.8

Update HyperHDR to version 0.0.8, adjust version warning cutoff to 21.0.0.0, and clean up imports in light and switch components.

# Integration v0.0.7

- Update most code to match changes present in the official Hyperion component as of 2024.07.4
- Retained code from v0.0.6 `light.py` since updating that to match Hyperion code breaks multiple aspects of the light entity
- Camera is still broken and remains disabled
    - If anyone can fix it then please do so and create a pull request!
    - See `__init__.py` for more info.

# Integration v0.0.6

Match changes present in the official Hyperion component as of ha-core-2022.05.2
Bump hyperhdr-py version

# Integration v0.0.5

Add support for entity categories.

# Integration v0.0.4

### Breaking changes

- removed camera (sensor) due to instability

### Remediation for existing installations

Only do the following if you are updating from an earlier version:

- Install v0.0.4
- Restart Home Assistant
- Remove the orphaned camera entity
  - go to Configuration > Devices & Services > Integrations
  - locate HyperHDR
  - click the '12 entities' link
  - select the checkbox next to the orphaned camera entity
  - click 'REMOVE SELECTED'
  - click 'REMOVE'

### Alternative remediation method (nuclear option)

Only do the following if you are unsuccessful with the previous steps:

- Install v0.0.4
- Delete the HyperHDR integration
  - go to Configuration > Devices & Services > Integrations > HyperHDR > 3-dots menu
  - click 'DELETE'
  - click 'OK'
- Restart Home Assistant
- Re-add the HyperHDR integration
<!-- {% endif %} -->
