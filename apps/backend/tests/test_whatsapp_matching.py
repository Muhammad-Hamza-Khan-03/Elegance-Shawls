"""Container-free: reference matching, the shared event contract and the off switch."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from repositories.enquiries import new_reference
from whatsapp import config as wa_config
from whatsapp.matching import InboundEvent, extract_reference, phone_from_jid

FIXTURES = Path(__file__).resolve().parents[2] / "whatsapp-bridge" / "fixtures"


def test_reference_is_found_anywhere_case_insensitively():
    ref = new_reference()
    assert extract_reference(f"Assalam o Alaikum\nRef: {ref}\nthanks") == ref
    assert extract_reference(f"ref {ref.lower()}") == ref
    assert extract_reference("ES-12 and XES-ABCDEF9") is None
    assert extract_reference(None) is None


def test_phone_only_for_classic_jids():
    assert phone_from_jid("923001234567@s.whatsapp.net") == "+923001234567"
    assert phone_from_jid("123@lid") is None


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("valid-*.json")))
def test_valid_bridge_fixtures_parse(name):
    InboundEvent.model_validate_json((FIXTURES / name).read_text())


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("invalid-*.json")))
def test_invalid_bridge_fixtures_are_rejected(name):
    with pytest.raises(ValidationError):
        InboundEvent.model_validate(json.loads((FIXTURES / name).read_text()))


def test_fixtures_exist():
    assert list(FIXTURES.glob("valid-*.json")) and list(FIXTURES.glob("invalid-*.json"))


def test_flag_defaults_off_and_consumer_exits_zero_when_disabled(monkeypatch):
    assert wa_config.is_enabled() is False and wa_config.misconfiguration() is None
    from whatsapp import consumer
    assert consumer.main() == 0


def test_enabled_without_token_or_redis_is_misconfigured(monkeypatch):
    from configuration.config import settings
    monkeypatch.setattr(settings, "whatsapp_bridge_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_bridge_token", "")
    assert "TOKEN" in wa_config.misconfiguration()
    from whatsapp import consumer
    assert consumer.main() == 1
