"""Enrichment suggestions: contract, provenance, photo refusal, privacy, approval boundary, offline; plus the eval gate."""
import hashlib
import importlib.util
import json
import socket
from pathlib import Path

import pytest

from semantic import enrichment as en

EVALS = Path(__file__).resolve().parents[3] / "evals"
spec = importlib.util.spec_from_file_location("enrichment_eval", EVALS / "enrichment_eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

DATASET = EVALS / "synthetic" / "enrichment_suggestions.jsonl"
PROVIDER = en.FakeEnrichmentProvider()
PRODUCT = {"name": "Synthetic Charcoal Silk Stole", "main_description": "Twill weave, owner@example.test 03001234567"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def no_net(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "socket", no_net)
    monkeypatch.setattr(socket, "create_connection", no_net)


def by_field(s):
    return {f.field: f for f in s.fields}


def test_text_suggestions_carry_provenance_and_identity():
    s = en.suggest(PROVIDER, PRODUCT)
    f = by_field(s)
    assert (f["colour"].value, f["colour"].source, f["colour"].evidence) == ("grey", "text", "charcoal")
    assert (f["material"].value, f["fabric"].value) == ("silk", "twill")
    assert all(x.outcome is en.Outcome.SUGGESTED and x.confidence == 0.9 and not x.needs_review for x in s.fields)
    assert (s.provider, s.model, s.version, s.status, s.auto_apply) == ("fake", "fake-enrich-v1", "1", en.PENDING, False)
    assert s == en.suggest(PROVIDER, PRODUCT) and len(s.input_hash) == 64


def test_input_hash_is_canonical_and_sensitive():
    base = en.suggest(PROVIDER, PRODUCT).input_hash
    assert en.suggest(PROVIDER, {**PRODUCT, "name": "  synthetic CHARCOAL silk stole "}).input_hash == base
    assert en.suggest(PROVIDER, PRODUCT, ["a", "b"]).input_hash == en.suggest(PROVIDER, PRODUCT, ["b", "a"]).input_hash
    assert en.suggest(PROVIDER, PRODUCT, ["a"]).input_hash != base
    assert en.suggest(PROVIDER, {**PRODUCT, "name": "Synthetic Navy Silk Stole"}).input_hash != base


def test_photo_inference_of_material_and_fabric_is_unsupported_not_guessed():
    s = en.suggest(PROVIDER, {"name": "Synthetic Shawl"}, ["img-1"])
    f = by_field(s)
    assert f["material"].outcome is f["fabric"].outcome is en.Outcome.UNSUPPORTED
    assert f["material"].value is None and f["material"].needs_review and f["material"].reason == "photo_inference_unsupported"
    assert f["colour"].source == "photo" and f["colour"].needs_review  # allowed, but never trusted without a human


def test_nothing_supported_is_unknown():
    s = en.suggest(PROVIDER, {"name": "Synthetic Plain Item"})
    assert all(f.outcome is en.Outcome.UNKNOWN and f.value is None and f.needs_review for f in s.fields)


class Scripted:
    name, model, version = "fake", "fake-enrich-v1", "1"

    def __init__(self, out):
        self.out = out

    def propose(self, text, photos, fields):
        if isinstance(self.out, Exception):
            raise self.out
        return self.out


@pytest.mark.parametrize("raw,reason", [
    ({"field": "colour", "value": "grey", "source": "text", "evidence": "not in text", "confidence": 0.9}, "evidence_not_found"),
    ({"field": "colour", "value": "grey", "source": "photo", "evidence": "other-img", "confidence": 0.9}, "evidence_not_found"),
    ({"field": "colour", "value": "chartreuse", "source": "text", "evidence": "silk", "confidence": 0.9}, "colour_not_in_vocabulary"),
    ({"field": "colour", "value": "grey", "source": "text", "evidence": "silk", "confidence": 1.5}, "invalid_provider_output"),
    ({"field": "colour", "value": "grey", "source": "text", "evidence": "silk", "confidence": float("nan")}, "invalid_provider_output"),
    ({"field": "colour", "value": "grey", "source": "guess", "evidence": "silk", "confidence": 0.9}, "invalid_provider_output"),
    ({"field": "colour", "value": "grey", "source": "text", "evidence": "", "confidence": 0.9}, "evidence_not_found"),
])
def test_invalid_provider_output_degrades_to_unknown(raw, reason):
    f = by_field(en.suggest(Scripted([raw]), {"name": "Synthetic silk"}, ["img-1"], ["colour"]))["colour"]
    assert f.outcome is en.Outcome.UNKNOWN and f.reason == reason and f.needs_review and f.value is None


def test_provider_failure_or_garbage_is_unknown_and_low_confidence_needs_review():
    for out in (RuntimeError("boom"), None, "garbage", [1, "x"]):
        s = en.suggest(Scripted(out), {"name": "Synthetic silk"}, fields=["material"])
        assert s.fields[0].outcome is en.Outcome.UNKNOWN and s.needs_review
    low = {"field": "material", "value": "Silk", "source": "text", "evidence": "silk", "confidence": 0.5}
    f = en.suggest(Scripted([low]), {"name": "Synthetic silk"}, fields=["material"]).fields[0]
    assert f.outcome is en.Outcome.SUGGESTED and f.value == "silk" and f.needs_review


def test_request_and_provider_are_validated():
    class Live(Scripted):
        name = "openai"
    with pytest.raises(en.EnrichmentError):
        en.suggest(Live([]), PRODUCT)
    for kw in ({"fields": []}, {"fields": ["price"]}, {"fields": ["colour", "colour"]},
               {"photos": ["https://x.test/a.jpg"]}, {"photos": ["a"] * 11}, {"photos": "img-1"}):
        with pytest.raises(en.EnrichmentError):
            en.suggest(PROVIDER, PRODUCT, **kw)
    with pytest.raises(en.EnrichmentError):
        en.suggest(PROVIDER, {"category": "shawls"})


def test_invariants_reject_inconsistent_suggestions():
    for args in ((en.Outcome.SUGGESTED, None, "text", "x", 0.9, False), (en.Outcome.SUGGESTED, "grey", None, "x", 0.9, False),
                 (en.Outcome.SUGGESTED, "grey", "text", "x", 0.2, False), (en.Outcome.UNKNOWN, "grey", None, None, 0.0, True),
                 (en.Outcome.UNSUPPORTED, None, None, None, 0.0, False), (en.Outcome.SUGGESTED, "grey", "text", "x", 2.0, True)):
        with pytest.raises(en.EnrichmentError):
            en.FieldSuggestion("colour", *args)


def test_private_data_never_reaches_provider_or_output():
    seen = []

    class Spy(Scripted):
        def propose(self, text, photos, fields):
            seen.append(text)
            return []
    s = en.suggest(Spy([]), {**PRODUCT, "customer_email": "buyer@example.test", "phone": "03111234567", "cost": 77})
    blob = seen[0] + repr(s)
    for needle in ("owner@", "buyer@", "03001234567", "03111234567", "77", "example.test"):
        assert needle not in blob


def test_approval_is_an_explicit_human_decision_and_applies_nothing():
    s = en.suggest(PROVIDER, {"name": "Synthetic Silk Shawl"})
    assert s.status == en.PENDING and not s.auto_apply
    ok = en.approve(s, " Aisha ", ["material"])
    assert ok == en.ApprovedEnrichment(s.input_hash, "Aisha", (("material", "silk"),))
    unsupported = en.suggest(PROVIDER, {"name": "Synthetic Shawl"}, ["img-1"])
    for args in ((s, "", ["material"]), (s, "  ", ["material"]), (s, None, ["material"]), (s, "a", []),
                 (s, "a", ["price"]), (s, "a", ["fabric"]), (unsupported, "a", ["material"])):
        with pytest.raises(en.EnrichmentError):
            en.approve(*args)
    assert not hasattr(en, "apply") and not hasattr(en, "publish")


# --- eval gate ---------------------------------------------------------------------------------------------

def shipped():
    raw = DATASET.read_bytes()
    pin = (EVALS / "synthetic" / "enrichment_suggestions.jsonl.sha256").read_text().split()[0]
    return raw, ev.load_cases(raw), pin


def unreviewed(cases):
    return [{**c, "reviewed": False} for c in cases]


def run(cases, pin=None):
    raw = "\n".join(json.dumps(c) for c in cases).encode()
    sha = hashlib.sha256(raw).hexdigest()
    return ev.evaluate(ev.load_cases(raw) if cases else [], PROVIDER, sha, sha if pin is None else pin)


def test_shipped_fixture_is_reviewed_pinned_covered_and_passes():
    raw, cases, pin = shipped()
    assert len(cases) >= 8 and all(c["reviewed"] is True for c in cases) and hashlib.sha256(raw).hexdigest() == pin
    r = ev.evaluate(cases, PROVIDER, pin, pin)
    assert r["metrics"]["field_accuracy"] == 1.0 and r["coverage"]["outcomes"] == ["suggested", "unknown", "unsupported"]
    assert r["status"] == "PASS" and r["release_ready"] is True and r["reasons"] == []
    assert ev.main([]) == 0 and ev.main(["--release-ready"]) == 0


def test_gate_blocks_empty_unreviewed_unpinned_and_incomplete():
    _, cases, _ = shipped()
    assert run([])["status"] == "NOT_EVALUATED" and not run([])["release_ready"]
    r = run(unreviewed(cases))                                                   # unreviewed copy
    assert r["status"] == "NOT_EVALUATED" and r["release_ready"] is False and r["reasons"] == ["cases not human-reviewed"]
    assert run(cases[:1])["reasons"] == ["coverage incomplete"]                  # reviewed but thin
    partial = run(cases, pin="")
    assert partial["status"] == "NOT_EVALUATED" and "dataset checksum is not pinned" in partial["reasons"]
    mixed = list(cases)
    mixed[0] = {**mixed[0], "reviewed": False}
    assert run(mixed)["release_ready"] is False


def test_gate_fails_on_threshold_miss_and_checksum_mismatch():
    _, cases, _ = shipped()
    wrong = list(cases)
    for i in (0, 1):
        wrong[i] = {**wrong[i], "expected": {**wrong[i]["expected"], "colour": {"outcome": "suggested", "value": "red"}}}
    r = run(wrong)
    assert r["status"] == "FAIL" and not r["release_ready"] and r["metrics"]["field_accuracy"] < 0.95
    tampered = run(cases, pin="0" * 64)
    assert tampered["status"] == "FAIL" and not tampered["release_ready"]


def test_hostile_provider_cannot_produce_photo_or_privacy_leaks_but_does_fail_the_gate():
    _, cases, _ = shipped()

    class Hostile(en.FakeEnrichmentProvider):
        def propose(self, text, photos, fields):
            return [{"field": f, "value": "wool", "source": "photo", "evidence": photos[0] if photos else "x",
                     "confidence": 1.0} for f in fields]
    r = ev.evaluate(cases, Hostile(), "x", "x")
    assert r["metrics"]["unsupported_photo_leaks"] == 0 and r["metrics"]["privacy_leaks"] == 0
    assert r["status"] == "FAIL" and r["release_ready"] is False


def test_eval_refuses_non_synthetic_and_is_reproducible():
    _, cases, pin = shipped()
    for bad in ({**cases[0], "synthetic": False}, {**cases[0], "id": "real-1"}):
        with pytest.raises(ev.NonSyntheticInput):
            ev.evaluate([bad], PROVIDER)
        with pytest.raises(ev.NonSyntheticInput):
            ev.load_cases(json.dumps(bad).encode())
    assert ev.main(["--dataset", str(EVALS / "datasets" / "filter_parsing.jsonl")]) == 2
    a, b = ev.evaluate(cases, PROVIDER, pin, pin), ev.evaluate(cases, PROVIDER, pin, pin)
    assert a == b and a["reproducibility"]["dataset_sha256"] == pin and a["reproducibility"]["cases"] == len(cases)
    assert a["reproducibility"]["enrichment_version"] == en.ENRICHMENT_VERSION and a["thresholds"] == ev.THRESHOLDS
