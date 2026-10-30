import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from semantic import embeddings as emb
from semantic import representation as rep

EVALS = Path(__file__).resolve().parents[3] / "evals"
spec = importlib.util.spec_from_file_location("semantic_eval", EVALS / "semantic_eval.py")
se = importlib.util.module_from_spec(spec)
spec.loader.exec_module(se)

PRODUCT = {"name": "  Wool  SHAWL ", "category": "shawls", "material": "Wool", "main_description": "Warm.",
           "variants": [{"name": "Grey", "color": "Grey", "size": "Free Size"}, {"name": "Blue", "color": "Blue"}]}
FAKE_ENV = {"SEMANTIC_EMBEDDING_PROVIDER": "fake", "SEMANTIC_EMBEDDING_MODEL": "fake-hash-v1",
            "SEMANTIC_EMBEDDING_DIMENSIONS": "64"}


def fake():
    return emb.FakeEmbeddingProvider(emb.load_config(FAKE_ENV, allow_test_providers=True))


def test_representation_is_deterministic_and_order_insensitive():
    a = rep.represent(PRODUCT)
    b = rep.represent({**PRODUCT, "name": "wool shawl", "variants": list(reversed(PRODUCT["variants"])) * 2})
    assert a == b and a["version"] == rep.REPRESENTATION_VERSION and len(a["fingerprint"]) == 64
    assert rep.represent({**PRODUCT, "material": "silk"})["fingerprint"] != a["fingerprint"]


def test_private_fields_and_contact_details_are_excluded():
    leaky = {**PRODUCT, "id": "uuid-1", "slug": "s-1", "item_number": "SKU-9", "cost": 111, "price": 222,
             "supplier": "acme", "source_url": "https://x.test/p", "customer_email": "a@b.co", "phone": "03001234567",
             "main_description": "Call 0300 1234567 or mail owner@shop.pk see https://x.test"}
    leaky["variants"] = [{"name": "Grey", "id": "v-1", "stock": 5, "price": 9, "internal_note": "secret-note"}]
    text = rep.represent(leaky)["text"]
    for needle in ("uuid-1", "s-1", "sku-9", "111", "222", "acme", "x.test", "a@b.co", "0300", "owner@", "secret-note", "v-1"):
        assert needle not in text
    assert "wool shawl" in text


def test_bounds_and_validation():
    big = rep.represent({"name": "n" * 1000, "main_description": "d" * 9000,
                         "variants": [{"name": f"v{i:03}", "description": "x" * 900} for i in range(80)]})
    assert len(big["text"]) <= rep.MAX_TEXT_CHARS
    assert big["text"].splitlines()[0] == "name: " + "n" * 160
    assert big["text"].count("\nvariant: ") <= rep.MAX_VARIANTS
    for bad in (None, [], {"category": "shawls"}, {"name": "  "}, {"name": "x", "variants": "no"}, {"name": "x", "variants": [1]}):
        with pytest.raises(rep.RepresentationError):
            rep.represent(bad)


def test_provider_config_fails_closed():
    assert emb.load_config({}) is None
    for env in ({**FAKE_ENV, "SEMANTIC_EMBEDDING_PROVIDER": "openai"},
                {**FAKE_ENV, "SEMANTIC_EMBEDDING_MODEL": "other"},
                {**FAKE_ENV, "SEMANTIC_EMBEDDING_DIMENSIONS": "65"},
                {**FAKE_ENV, "SEMANTIC_EMBEDDING_DIMENSIONS": ""},
                {"SEMANTIC_EMBEDDING_PROVIDER": "fake"}):
        with pytest.raises(emb.EmbeddingConfigError):
            emb.load_config(env, allow_test_providers=True)
    with pytest.raises(emb.EmbeddingConfigError):          # fake needs the explicit test opt-in
        emb.load_config(FAKE_ENV)


@pytest.mark.parametrize("vec,code", [("abc", "not_a_sequence"), (None, "not_a_sequence"), ([1.0] * 3, "wrong_dimension"),
                                      ([float("nan")] * 4, "non_finite"), ([float("inf")] + [0.0] * 3, "non_finite"),
                                      (["a"] * 4, "non_numeric"), ([True] * 4, "non_numeric")])
def test_vector_validation_errors_are_deterministic(vec, code):
    with pytest.raises(emb.VectorError) as e:
        emb.validate_vector(vec, 4)
    assert e.value.code == code
    assert emb.validate_vector([1, 2.5, 0, -1], 4) == (1.0, 2.5, 0.0, -1.0)


def test_fake_vectors_are_stable_across_processes_and_offline(monkeypatch):
    def no_net(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "socket", no_net)
    v = fake().embed("wool shawl")
    assert v == fake().embed("wool shawl") and v != fake().embed("silk scarf") and len(v) == 64
    assert abs(sum(x * x for x in v) - 1) < 1e-9
    code = ("from semantic.embeddings import *;c=load_config({'SEMANTIC_EMBEDDING_PROVIDER':'fake',"
            "'SEMANTIC_EMBEDDING_MODEL':'fake-hash-v1','SEMANTIC_EMBEDDING_DIMENSIONS':'64'},allow_test_providers=True);"
            "print(FakeEmbeddingProvider(c).embed('wool shawl')[:3])")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         cwd=Path(__file__).resolve().parents[1], env={"PYTHONHASHSEED": "123"}).stdout
    assert out.strip() == str(v[:3])


def synthetic(**over):
    case = {"id": "syn-1", "synthetic": True, "reviewed": True, "query": "wool shawl",
            "corpus": [{"id": "syn-p1", "name": "Wool Shawl"}, {"id": "syn-p2", "name": "Silk Scarf"}], "relevant": ["syn-p1"]}
    return {**case, **over}


def test_evaluator_refuses_non_synthetic_input():
    for c in (synthetic(synthetic=False), synthetic(id="real-1"), synthetic(corpus=[{"id": "p1", "name": "x"}]),
              {k: v for k, v in synthetic().items() if k != "synthetic"}):
        with pytest.raises(se.NonSyntheticInput):
            se.load_cases(json.dumps(c).encode())
    assert se.main(["--dataset", str(EVALS / "datasets" / "filter_parsing.jsonl")]) == 2
    with pytest.raises(se.NonSyntheticInput):
        se.evaluate([synthetic(id="real-direct")], fake())


def test_empty_evaluation_blocks_release_and_fake_is_never_evidence():
    empty = se.evaluate([], fake())
    assert empty["status"] == "NOT_EVALUATED" and empty["release_ready"] is False
    reviewed = se.evaluate(se.load_cases(json.dumps(synthetic()).encode()), fake())
    assert reviewed["release_ready"] is False and reviewed["status"] == "NOT_EVALUATED"
    unreviewed = se.evaluate([synthetic(reviewed=False)], fake())
    assert unreviewed["release_ready"] is False
    assert se.main([]) == 0 and se.main(["--release-ready"]) == 3


def test_release_ready_needs_reviewed_non_test_provider(monkeypatch):
    class Live:  # stand-in for a future allowlisted provider; not reachable from the CLI
        config = emb.EmbeddingConfig("live", "m", 64)
        embed = staticmethod(fake().embed)
    assert se.evaluate([synthetic()], Live())["release_ready"] is True
    assert se.evaluate([synthetic(reviewed=False)], Live())["release_ready"] is False
    assert se.evaluate([], Live())["release_ready"] is False


def test_report_is_reproducible():
    cases = se.load_cases((EVALS / "synthetic" / "semantic_retrieval.jsonl").read_bytes())
    a, b = se.evaluate(cases, fake(), "x"), se.evaluate(cases, fake(), "x")
    assert a == b and a["reproducibility"]["representation_version"] == rep.REPRESENTATION_VERSION
    assert a["reproducibility"]["cases"] == len(cases) and a["release_ready"] is False
