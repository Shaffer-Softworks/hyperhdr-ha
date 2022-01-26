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
  - click the _12 entities_ link
  - select the checkbox next to the orphaned camera entity
  - click _REMOVE SELECTED_
  - click _REMOVE_

## Alternative remediation method (nuclear option)

Only do the following if you are unsuccessful with the previous steps:

- Install v0.0.4
- Delete the HyperHDR integration
  - go to Configuration > Devices & Services > Integrations > HyperHDR > 3-dots menu
  - click _DELETE_
  - click _OK_
- Restart Home Assistant
- Re-add the HyperHDR integration
