# Apollo AIR-1 Air Quality Automation — Review & Suggestions

## Summary

The automation monitors an Apollo AIR-1 VOC sensor and escalates alerts (lighting, fan speed, WLED presets, notifications) based on air quality severity. When conditions return to normal, it restores previous device states. Overall it is well-structured, but there are several bugs, race conditions, and opportunities for simplification.

---

## Bugs & Issues

### 1. `scene_exists` checks the wrong scene entity

```yaml
scene_exists: "{{ states.scene.air_alert_previous_devices_v2 is not none }}"
```

The scene you actually **create** is `air_alert_previous_devices`, but the variable checks for `air_alert_previous_devices_v2`. This means `scene_exists` will almost always be `false`, causing `should_snapshot` to be `true` on every trigger — even when escalating from "Abnormal" to "Severe." That defeats the purpose of protecting the snapshot.

**Fix:**

```yaml
scene_exists: "{{ states.scene.air_alert_previous_devices is not none }}"
```

### 2. `saved_wled_preset` is referenced as a bare variable instead of a state lookup in the Normal branch

In the "Normal" restore branch, the condition template references:

```yaml
value_template: |-
  {{
    saved_wled_preset not in
    ['unknown', 'unavailable', 'none', 'None', '']
  }}
```

This works because `saved_wled_preset` is defined in the top-level `variables` block. However, the `select.select_option` action then references it as:

```yaml
option: "{{ saved_wled_preset }}"
```

This is **correct** since the variable is in scope. No issue here — just noting it for clarity. The pattern is consistent.

### 3. Escalation from "Abnormal" to "Severe" overwrites the snapshot

If air quality goes Normal → Abnormal → Severe, the automation triggers the "severe" branch. Because `should_snapshot` is (incorrectly) always `true` due to bug #1, it will overwrite the scene snapshot with the already-alerting device states (orange light, medium fan). When quality returns to normal, it restores the *alert state* instead of the original state.

Even with bug #1 fixed, the `should_snapshot` logic still has a gap: `from_state` checks for `'Normal', 'Improved', 'unknown', 'unavailable', 'none', ''` — the state `Abnormal` is not in that list, so `should_snapshot` would be `false` during escalation (which is correct). But `from_state` also doesn't include `Very abnormal` or `Extremely abnormal`, so de-escalation (Severe → Abnormal) would also *not* snapshot — which is the desired behavior.

**Once bug #1 is fixed, the escalation logic is actually correct.** The `from_state` check properly prevents re-snapshotting during alert-to-alert transitions.

### 4. No `for` duration on triggers — sensor flicker can cause false alerts

Momentary state flickers (sensor noise, integration reloads, etc.) will trigger the full automation. Consider adding a `for` duration:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.apollo_air_1_2c5998_voc_quality
    to: Abnormal
    id: abnormal
    for: "00:00:30"
```

This ensures the sensor must remain in the abnormal state for 30 seconds before triggering. Adjust the duration to your preference. Note: you may want a shorter or no delay for the "Normal" trigger so restoration is snappy.

### 5. No rate limiting / cooldown on notifications

With `mode: restart`, rapid state changes (e.g., sensor bouncing between states) can flood notifications. Consider:
- Adding an `input_datetime` helper to track the last notification time
- Using a condition to suppress notifications within a cooldown period
- Or wrapping the notification in a script with `mode: single`

---

## Structural Improvements

### 6. Extract the snapshot logic into a reusable script

The snapshot block is **duplicated identically** in both the "abnormal" and "severe" branches. This violates DRY and makes maintenance error-prone. Extract it into a script:

```yaml
# scripts.yaml
air_quality_snapshot_devices:
  alias: "Snapshot Air Quality Alert Devices"
  sequence:
    - action: scene.create
      continue_on_error: true
      data:
        scene_id: air_alert_previous_devices
        snapshot_entities:
          - light.apollo_air_1_2c5998_rgb_light
          - light.wled_2
          - fan.switchbot_air_purifier
    - choose:
        - conditions:
            - condition: template
              value_template: |-
                {{
                  states('select.wled_preset_2') not in
                  ['unknown', 'unavailable', 'none', 'None', '']
                }}
          sequence:
            - action: input_text.set_value
              continue_on_error: true
              target:
                entity_id: input_text.wled_2_previous_preset
              data:
                value: "{{ states('select.wled_preset_2') }}"
      default:
        - action: input_text.set_value
          continue_on_error: true
          target:
            entity_id: input_text.wled_2_previous_preset
          data:
            value: ""
```

Then in the automation, both branches simply call:

```yaml
- action: script.air_quality_snapshot_devices
```

### 7. Consider moving snapshot logic before the `choose` block

Since both alert branches do the same snapshot conditionally, you could snapshot *once* before the `choose`, then the `choose` only handles the alert-level-specific actions (light color, fan speed, WLED preset, notification message):

```yaml
actions:
  # Step 1: Snapshot if transitioning from a non-alert state
  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ trigger.id in ['abnormal', 'severe'] and should_snapshot }}
        sequence:
          - action: script.air_quality_snapshot_devices

  # Step 2: Handle the specific alert level
  - choose:
      - conditions:
          - condition: trigger
            id: normal
        sequence:
          # ... restore logic ...
      - conditions:
          - condition: trigger
            id: abnormal
        sequence:
          # ... abnormal alert actions (no snapshot here) ...
      - conditions:
          - condition: trigger
            id: severe
        sequence:
          # ... severe alert actions (no snapshot here) ...
```

### 8. Add a `default` branch to the main `choose`

If none of the conditions match (e.g., an unexpected sensor state), the automation silently does nothing. Adding a default with logging helps with debugging:

```yaml
default:
  - action: system_log.write
    data:
      message: >-
        Air quality automation: unhandled state
        "{{ states('sensor.apollo_air_1_2c5998_voc_quality') }}"
        (trigger: {{ trigger.id }})
      level: warning
```

---

## Minor Suggestions

### 9. Use `trigger.to_state.state` instead of a separate state condition

The `abnormal` and `severe` branches each have both a trigger condition AND a state condition checking the same entity. The state condition is a safeguard against `mode: restart` edge cases and is a valid defensive pattern — but you could simplify with:

```yaml
- condition: template
  value_template: "{{ trigger.to_state.state == 'Abnormal' }}"
```

This is functionally equivalent and slightly more readable.

### 10. Consider using `input_select` instead of `input_text` for WLED preset

If the set of WLED presets is known and fixed, `input_select` provides validation and a dropdown in the UI. If presets can be arbitrary strings, `input_text` is fine.

### 11. Add `max_exceeded: silent` if you don't want restart warnings in the log

```yaml
mode: restart
max_exceeded: silent
```

### 12. The delay before restoring WLED preset could be fragile

```yaml
- delay: "00:00:01"
- action: select.select_option
  target:
    entity_id: select.wled_preset_2
  data:
    option: "{{ saved_wled_preset }}"
```

If the scene restoration takes longer than 1 second for WLED, the preset could be overwritten. Consider using `wait_template` or a longer delay, or listen for a state change confirmation.

---

## Improved Automation (Full YAML)

Below is the refactored automation incorporating all fixes:

```yaml
alias: Apollo AIR-1 Air Quality Alert
description: >-
  Monitors the Apollo AIR-1 VOC sensor for air quality changes.
  Activates alerts with escalating severity (lighting, fan, WLED, notifications).
  Restores previous device states when quality returns to normal.

triggers:
  - trigger: state
    entity_id: sensor.apollo_air_1_2c5998_voc_quality
    to: Abnormal
    id: abnormal
    for: "00:00:30"
  - trigger: state
    entity_id: sensor.apollo_air_1_2c5998_voc_quality
    to: Very abnormal
    id: severe
    for: "00:00:30"
  - trigger: state
    entity_id: sensor.apollo_air_1_2c5998_voc_quality
    to: Extremely abnormal
    id: severe
    for: "00:00:30"
  - trigger: state
    entity_id: sensor.apollo_air_1_2c5998_voc_quality
    to: Normal
    id: normal
  - trigger: state
    entity_id: sensor.apollo_air_1_2c5998_voc_quality
    to: Improved
    id: normal

mode: restart
max_exceeded: silent

variables:
  from_state: >-
    {% if trigger is defined and trigger.from_state is defined and
    trigger.from_state is not none %}
      {{ trigger.from_state.state }}
    {% else %}
      unknown
    {% endif %}
  scene_exists: "{{ states.scene.air_alert_previous_devices is not none }}"
  saved_wled_preset: "{{ states('input_text.wled_2_previous_preset') }}"
  should_snapshot: |-
    {{
      from_state in ['Normal', 'Improved', 'unknown', 'unavailable', 'none', '']
      or not scene_exists
    }}

actions:
  # Snapshot devices before alerting (shared by both alert levels)
  - choose:
      - conditions:
          - condition: template
            value_template: >-
              {{ trigger.id in ['abnormal', 'severe'] and should_snapshot }}
        sequence:
          - action: scene.create
            continue_on_error: true
            data:
              scene_id: air_alert_previous_devices
              snapshot_entities:
                - light.apollo_air_1_2c5998_rgb_light
                - light.wled_2
                - fan.switchbot_air_purifier
          - choose:
              - conditions:
                  - condition: template
                    value_template: |-
                      {{
                        states('select.wled_preset_2') not in
                        ['unknown', 'unavailable', 'none', 'None', '']
                      }}
                sequence:
                  - action: input_text.set_value
                    continue_on_error: true
                    target:
                      entity_id: input_text.wled_2_previous_preset
                    data:
                      value: "{{ states('select.wled_preset_2') }}"
            default:
              - action: input_text.set_value
                continue_on_error: true
                target:
                  entity_id: input_text.wled_2_previous_preset
                data:
                  value: ""

  # Handle the specific state
  - choose:
      # --- NORMAL: Restore previous state ---
      - conditions:
          - condition: trigger
            id: normal
        sequence:
          - action: scene.turn_on
            continue_on_error: true
            target:
              entity_id: scene.air_alert_previous_devices
            data: {}
          - choose:
              - conditions:
                  - condition: template
                    value_template: |-
                      {{
                        saved_wled_preset not in
                        ['unknown', 'unavailable', 'none', 'None', '']
                      }}
                sequence:
                  - delay: "00:00:02"
                  - action: select.select_option
                    continue_on_error: true
                    target:
                      entity_id: select.wled_preset_2
                    data:
                      option: "{{ saved_wled_preset }}"

      # --- ABNORMAL: Warning-level alert ---
      - conditions:
          - condition: trigger
            id: abnormal
          - condition: state
            entity_id: sensor.apollo_air_1_2c5998_voc_quality
            state: Abnormal
        sequence:
          - action: light.turn_on
            continue_on_error: true
            target:
              entity_id: light.apollo_air_1_2c5998_rgb_light
            data:
              rgb_color: [255, 140, 0]
              brightness_pct: 100
              effect: Slow Pulse
          - action: fan.set_preset_mode
            continue_on_error: true
            target:
              entity_id: fan.switchbot_air_purifier
            data:
              preset_mode: medium
          - action: select.select_option
            continue_on_error: true
            target:
              entity_id: select.wled_preset_2
            data:
              option: Blink Rainbow Orange
          - action: script.send_notification_to_all_devices
            continue_on_error: true
            data:
              title: "⚠️ Air Quality Alert!"
              message: Abnormal air quality in the office

      # --- SEVERE: Critical-level alert ---
      - conditions:
          - condition: trigger
            id: severe
          - condition: state
            entity_id: sensor.apollo_air_1_2c5998_voc_quality
            state:
              - Very abnormal
              - Extremely abnormal
        sequence:
          - action: light.turn_on
            continue_on_error: true
            target:
              entity_id: light.apollo_air_1_2c5998_rgb_light
            data:
              rgb_color: [255, 0, 0]
              brightness_pct: 100
              effect: Fast Pulse
          - action: fan.set_preset_mode
            continue_on_error: true
            target:
              entity_id: fan.switchbot_air_purifier
            data:
              preset_mode: high
          - action: select.select_option
            continue_on_error: true
            target:
              entity_id: select.wled_preset_2
            data:
              option: Blink Rainbow
          - action: script.send_notification_to_all_devices
            continue_on_error: true
            data:
              title: "🚨 Air Quality Alert!"
              message: Severe air quality in the office

    # Catch unhandled states for debugging
    default:
      - action: system_log.write
        data:
          message: >-
            Air quality automation: unhandled state
            "{{ states('sensor.apollo_air_1_2c5998_voc_quality') }}"
            (from: {{ from_state }}, trigger: {{ trigger.id }})
          level: warning
```

---

## Checklist of Changes

| # | Issue | Severity | Fixed In Improved YAML |
|---|-------|----------|----------------------|
| 1 | `scene_exists` checks wrong entity (`_v2`) | **Bug** | Yes |
| 2 | Variable scoping verified | Info | N/A |
| 3 | Escalation overwrites snapshot (caused by #1) | **Bug** | Yes (via #1 fix) |
| 4 | No `for` duration — sensor flicker risk | Medium | Yes (30s delay) |
| 5 | No notification rate limiting | Low | Noted (not in YAML) |
| 6 | Duplicated snapshot logic | Maintainability | Yes (hoisted above choose) |
| 7 | Snapshot before choose | Structural | Yes |
| 8 | No default branch | Debugging | Yes |
| 9 | Redundant state conditions | Minor | Kept (defensive) |
| 10 | `input_text` vs `input_select` for presets | Minor | Noted |
| 11 | Missing `max_exceeded: silent` | Minor | Yes |
| 12 | 1s WLED restore delay may be too short | Minor | Increased to 2s |
