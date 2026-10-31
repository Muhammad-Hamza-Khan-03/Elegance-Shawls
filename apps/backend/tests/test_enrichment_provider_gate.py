"""The live-provider smoke refuses unless every gate is explicit and the input is the synthetic fixture. No network."""
import asyncio
import importlib.util
import json
import socket
from pathlib import Path

import pytest

from llm.fake import ProviderReply
from tests.test_enrichment_service import good_reply

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "enrichment_provider_smoke.py"
spec = importlib.util.spec_from_file_location("enrichment_provider_smoke", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

OPEN = {"P1_S3_PROVIDER_SMOKE": "1", "P1_S3_SYNTHETIC_ONLY": "1", "P1_S3_PROVIDER": "groq", "P1_S3_MODEL": "some-model",
        "GROQ_API_KEY": "SECRET-KEY"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))


class Counting:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    async def __call__(self, model, messages, timeout):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return ProviderReply(reply, cost_usd=0.001)


def go(env, complete):
    return asyncio.run(smoke.run(env, complete))


def test_gate_opens_only_with_every_explicit_switch():
    assert smoke.check_gate(OPEN) == ("groq", "some-model")
    assert smoke.check_gate({**OPEN, "P1_S3_PROVIDER": "gemini", "GEMINI_API_KEY": "k"}) == ("gemini", "some-model")


@pytest.mark.parametrize("drop", ["P1_S3_PROVIDER_SMOKE", "P1_S3_SYNTHETIC_ONLY", "P1_S3_PROVIDER", "P1_S3_MODEL", "GROQ_API_KEY"])
def test_a_missing_switch_refuses_with_zero_calls(drop, capsys):
    env = {k: v for k, v in OPEN.items() if k != drop}
    complete = Counting(good_reply())
    assert go(env, complete) == 2 and complete.calls == 0
    assert "REFUSED" in capsys.readouterr().out


@pytest.mark.parametrize("override", [{"P1_S3_PROVIDER_SMOKE": "true"}, {"P1_S3_SYNTHETIC_ONLY": "0"}, {"P1_S3_PROVIDER": "openrouter"},
                                      {"P1_S3_PROVIDER": "Groq"}, {"P1_S3_MODEL": ""}, {"P1_S3_MODEL": "a b; rm -rf"}])
def test_invalid_switch_values_refuse(override):
    with pytest.raises(smoke.GateError):
        smoke.check_gate({**OPEN, **override})


def test_the_bundled_fixture_is_synthetic():
    assert smoke.load_fixture()["name"].startswith("Sample")


@pytest.mark.parametrize("data", [{"product": {}}, {"synthetic": False, "id": "synthetic-x", "product": {}},
                                  {"synthetic": True, "id": "prod-123", "product": {}}, {"synthetic": "yes", "id": "synthetic-x", "product": {}}])
def test_a_non_synthetic_fixture_is_rejected(tmp_path, data):
    path = tmp_path / "f.json"
    path.write_text(json.dumps(data))
    with pytest.raises(smoke.GateError):
        smoke.load_fixture(path)


def test_run_makes_at_most_two_calls_and_prints_no_secrets_or_responses(capsys):
    complete = Counting(ConnectionError("SECRET-ERR"), ConnectionError("SECRET-ERR"), good_reply())
    assert go(OPEN, complete) == 1 and complete.calls == 2
    out = capsys.readouterr().out
    assert "FAILED" in out and "SECRET" not in out


def test_run_success_reports_counts_only(capsys):
    complete = Counting(good_reply())
    assert go(OPEN, complete) == 0 and complete.calls == 1
    out = capsys.readouterr().out
    assert "SUCCEEDED" in out and "light stole" not in out and "SECRET-KEY" not in out


def test_the_smoke_has_no_database_dependency():
    assert "database" not in SCRIPT.read_text().replace("no database", "")
