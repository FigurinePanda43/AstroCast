"""The automation blueprints shipped in blueprints/automation/astrocast."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml_dict
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

SOURCE = Path(__file__).parent.parent / "blueprints" / "automation" / "astrocast"
BLUEPRINTS = sorted(p.name for p in SOURCE.glob("*.yaml"))


def _entity(hass: HomeAssistant, key: str) -> str:
    registry = er.async_get(hass)
    return next(e.entity_id for e in registry.entities.values() if e.unique_id.endswith(f"_{key}"))


@pytest.fixture
def phone(hass: HomeAssistant) -> str:
    """A Companion app device to notify."""
    entry = MockConfigEntry(domain="mobile_app", data={"device_name": "Phone"})
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mobile_app", "phone")}, name="Phone"
    )
    return device.id


@pytest.fixture
def blueprints(hass: HomeAssistant) -> None:
    target = Path(hass.config.path("blueprints/automation/astrocast"))
    target.mkdir(parents=True, exist_ok=True)
    for name in BLUEPRINTS:
        shutil.copy(SOURCE / name, target / name)


def _inputs(hass: HomeAssistant, phone: str) -> dict[str, dict[str, Any]]:
    return {
        "observing_window.yaml": {
            "windows_calendar": _entity(hass, "observing_windows"),
            "notify_device": phone,
        },
        "favorite_window.yaml": {
            "favorite": _entity(hass, "favorite_M31"),
            "notify_device": phone,
            "language": "fr",
        },
        "astronomical_event.yaml": {
            "events_calendar": _entity(hass, "astronomy_events"),
            "keywords": "Maximum, eclipse",
            "notify_device": phone,
        },
        "tonight_briefing.yaml": {
            "score_sensor": _entity(hass, "deep_sky_tonight"),
            "notify_device": phone,
            "language": "fr",
        },
        "dew_heaters.yaml": {
            "dew_risk": _entity(hass, "dew_risk"),
            "heaters": ["input_boolean.heater"],
        },
    }


async def _setup(hass: HomeAssistant, phone: str) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"heater": {}}})
    inputs = _inputs(hass, phone)
    assert set(inputs) == set(BLUEPRINTS)
    config = {
        "automation": [
            {
                "id": name.removesuffix(".yaml"),
                "alias": name.removesuffix(".yaml"),
                "use_blueprint": {"path": f"astrocast/{name}", "input": values},
            }
            for name, values in inputs.items()
        ]
    }
    assert await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()


async def _stop(hass: HomeAssistant) -> None:
    """Detach the triggers (the calendar trigger keeps a refresh timer)."""
    await hass.services.async_call("automation", "turn_off", {"entity_id": "all"}, blocking=True)
    await hass.async_block_till_done()


async def test_blueprints_are_valid(
    hass: HomeAssistant, setup_integration, blueprints, phone
) -> None:
    """Every blueprint creates a working automation."""
    await _setup(hass, phone)
    try:
        for name in BLUEPRINTS:
            state = hass.states.get(f"automation.{name.removesuffix('.yaml')}")
            assert state is not None, name
            assert state.state == "on", (name, state.attributes)
    finally:
        await _stop(hass)


async def test_dew_heaters_follow_the_risk(
    hass: HomeAssistant, setup_integration, blueprints, phone
) -> None:
    await _setup(hass, phone)
    try:
        risk = _entity(hass, "dew_risk")
        hass.states.async_set("sun.sun", "below_horizon")
        hass.states.async_set(risk, "moderate")
        await hass.async_block_till_done()
        assert hass.states.get("input_boolean.heater").state == "on"
        hass.states.async_set(risk, "low")
        await hass.async_block_till_done()
        assert hass.states.get("input_boolean.heater").state == "off"
        # Not during the day.
        hass.states.async_set("sun.sun", "above_horizon")
        hass.states.async_set(risk, "high")
        await hass.async_block_till_done()
        assert hass.states.get("input_boolean.heater").state == "off"
    finally:
        await _stop(hass)


def _blueprint(name: str) -> dict[str, Any]:
    return load_yaml_dict(SOURCE / name)


def _render(hass: HomeAssistant, template: str, variables: dict[str, Any]) -> str:
    return Template(template, hass).async_render(variables, parse_result=False)


async def test_briefing_message(hass: HomeAssistant, setup_integration) -> None:
    data = _blueprint("tonight_briefing.yaml")
    sensor = _entity(hass, "deep_sky_tonight")
    state = hass.states.get(sensor)
    action = data["actions"][0]
    for lang in ("fr", "en"):
        variables = {
            "texts": data["variables"]["texts"],
            "lang": lang,
            "sensor": sensor,
            "score": int(state.state),
        }
        title = _render(hass, action["title"], variables)
        message = _render(hass, action["message"], variables)
        assert f"{state.state}/100" in title
        assert ("Meilleure fenêtre" if lang == "fr" else "Best window") in message
        assert " h" in message and "→" in message
        if state.attributes.get("dew_onset"):
            assert ("Rosée vers" if lang == "fr" else "Dew around") in message
        assert "{" not in message


async def test_notification_messages(hass: HomeAssistant, setup_integration) -> None:
    window = _blueprint("observing_window.yaml")["actions"][0]
    trigger = {
        "calendar_event": {
            "summary": "Fenêtre ciel profond – bonne (68/100)",
            "description": "Séance de 4 h 15 (qualité 72/100).",
            "start": "2026-10-13T19:30:00+00:00",
            "end": "2026-10-13T23:45:00+00:00",
        }
    }
    message = _render(hass, window["message"], {"trigger": trigger})
    assert "→" in message and "Séance de 4 h 15" in message

    favorite = _blueprint("favorite_window.yaml")
    sensor = _entity(hass, "favorite_M31")
    variables = {"favorite": sensor, "lang": "fr", "minimum_score": 0}
    for key in ("name", "score", "start", "end"):
        variables[key] = _render(hass, favorite["variables"][key], variables)
    assert variables["name"]
    text = _render(hass, favorite["actions"][0]["message"], variables)
    assert text.startswith("Fenêtre favorable")

    event = _blueprint("astronomical_event.yaml")
    condition = event["conditions"][0]["value_template"]
    shower = {"calendar_event": {"summary": "Maximum des Orionides"}}
    phase = {"calendar_event": {"summary": "Pleine Lune"}}
    assert _render(hass, condition, {"keywords": "maximum, éclipse", "trigger": shower}) == "True"
    assert _render(hass, condition, {"keywords": "maximum, éclipse", "trigger": phase}) == "False"
    assert _render(hass, condition, {"keywords": "", "trigger": phase}) == "True"
