<!-- {% if not installed %} -->

## Installation

1. Add <https://github.com/mjoshd/hyperhdr-ha> to your [HACS](https://hacs.xyz/) custom repositories.
1. Choose `Integration` from the category selection.
1. Click install.
1. Restart Home Assistant.

## Configuration

1. In Home Assistant navigate to `Configuration` -> `Devices & Services` -> `Integrations`.
1. Click the `+ Add Integration` button.
1. Search for `HyperHDR`.
1. Enter the IP of your HyperHDR instance.
1. Click the `Submit` button.

<!-- {% endif %} -->

<!-- {% if installed %} -->
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
