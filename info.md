<!-- {% if not installed %} -->

## Installation

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

## Configuration

1. In Home Assistant navigate to `Configuration` -> `Devices & Services` -> `Integrations`.
1. Click the `+ Add Integration` button.
1. Search for `HyperHDR`.
1. If you cannot find `HyperHDR` in the list then be sure to clear your browser cache and/or perform a hard-refresh of the page.
1. Enter the IP address of your HyperHDR instance.
1. Click the `Submit` button.

<!-- {% endif %} -->

<!-- {% if installed %} -->
# Integration v0.0.7

- Update most code to match changes present in the official Hyperion component as of 2024.07.4
- Retained code from v0.0.6 `light.py` since updating that to match Hyperion code breaks multiple aspects of the light entity
- Camera is still broken and remains disabled
    - If anyoneone can fix it then please do so and create a pull request!
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
