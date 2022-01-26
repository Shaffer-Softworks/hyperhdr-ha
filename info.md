# Integration v0.0.4

## Breaking changes

- removed camera (sensor) due to instability

## Remediation for existing installations

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

## Alternative remediation method (nuclear option)

Only do the following if you are unsuccessful with the previous steps:

- Install v0.0.4
- Delete the HyperHDR integration
  - go to Configuration > Devices & Services > Integrations > HyperHDR > 3-dots menu
  - click 'DELETE'
  - click 'OK'
- Restart Home Assistant
- Re-add the HyperHDR integration
