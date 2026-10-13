# Automation and script examples

Replace `garden` with the name of your site (entity ids are built from it) and
`notify.mobile_app_phone` with your notifier.

## Warn me two hours before a good observing window

The *Observing windows* calendar contains every window whose score reaches the threshold set
in the options (deep sky and planetary).

```yaml
- alias: "AstroCast – window in 2 hours"
  triggers:
    - trigger: calendar
      event: start
      offset: "-2:00:00"
      entity_id: calendar.garden_observing_windows
  actions:
    - action: notify.mobile_app_phone
      data:
        title: "🔭 {{ trigger.calendar_event.summary }}"
        message: >-
          From {{ as_timestamp(trigger.calendar_event.start) | timestamp_custom('%H:%M') }}
          to {{ as_timestamp(trigger.calendar_event.end) | timestamp_custom('%H:%M') }}.
          {{ trigger.calendar_event.description }}
```

## Evening summary at 17:00

```yaml
- alias: "AstroCast – tonight"
  triggers:
    - trigger: time
      at: "17:00:00"
  conditions:
    - condition: numeric_state
      entity_id: sensor.garden_deep_sky_tonight
      above: 54
  actions:
    - action: notify.mobile_app_phone
      data:
        title: "Tonight: {{ states('sensor.garden_deep_sky_tonight') }}/100"
        message: >-
          Best window {{ as_timestamp(state_attr('sensor.garden_deep_sky_tonight', 'window_start')) | timestamp_custom('%H:%M') }}–{{ as_timestamp(state_attr('sensor.garden_deep_sky_tonight', 'window_end')) | timestamp_custom('%H:%M') }},
          Moon {{ state_attr('sensor.garden_deep_sky_tonight', 'moon_illumination') }} %,
          best target: {{ states('sensor.garden_best_target_tonight') }}.
```

## Switch the garden lights off during astronomical night (when it is clear)

```yaml
- alias: "AstroCast – dark garden"
  triggers:
    - trigger: state
      entity_id: binary_sensor.garden_astronomical_night
      to: "on"
  conditions:
    - condition: state
      entity_id: binary_sensor.garden_good_observing_conditions
      state: "on"
  actions:
    - action: light.turn_off
      target:
        area_id: garden
```

The astronomical-night sensor switches at the exact instant of astronomical dusk and dawn.

## Meteor shower reminder

```yaml
- alias: "AstroCast – meteor shower tomorrow"
  triggers:
    - trigger: calendar
      event: start
      offset: "-24:00:00"
      entity_id: calendar.garden_astronomical_events
  conditions:
    - "{{ 'meteor' in trigger.calendar_event.summary | lower or 'météores' in trigger.calendar_event.summary | lower }}"
  actions:
    - action: notify.mobile_app_phone
      data:
        title: "☄️ {{ trigger.calendar_event.summary }}"
        message: "{{ trigger.calendar_event.description }}"
```

## A favourite object becomes favourable

Each favourite has a timestamp sensor with its next favourable window (here M 42):

```yaml
- alias: "AstroCast – Orion Nebula"
  triggers:
    - trigger: time
      at:
        entity_id: sensor.garden_m_42_orion_nebula_next_window
        offset: "-01:00:00"
  actions:
    - action: notify.mobile_app_phone
      data:
        message: >-
          The Orion Nebula is well placed in one hour
          (score {{ state_attr('sensor.garden_m_42_orion_nebula_next_window', 'next_window_score') }}).
```

## Using the actions in a script

```yaml
script:
  when_is_jupiter_best:
    sequence:
      - action: astrocast.get_object_visibility
        data:
          config_entry_id: 0123456789abcdef0123456789abcdef
          object: Jupiter
        response_variable: result
      - action: notify.mobile_app_phone
        data:
          message: >-
            Best night for Jupiter: {{ result.best_night.date }}
            around {{ as_timestamp(result.best_night.best_time) | timestamp_custom('%H:%M') }}
            (score {{ result.best_night.score }}).
```

`astrocast.get_forecast` returns the nights (scores, windows, weather summary, top objects) and
the upcoming notable events, which is convenient for voice assistants or LLM-based
conversation agents.
