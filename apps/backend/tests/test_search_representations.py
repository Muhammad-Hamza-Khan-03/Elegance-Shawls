"""P1-S4a: deterministic catalogue text representations, privacy exclusion and the hybrid fixture/eval state."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from search import representations as rep
from search.representations import (REPRESENTATION_VERSION, RepresentationTooLong, clean, product_representation,
                                    variant_representation)

EVALS = Path(__file__).resolve().parents[3] / "evals"
spec = importlib.util.spec_from_file_location("run_hybrid_retrieval_evals", EVALS / "run_hybrid_retrieval_evals.py")
hybrid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hybrid)
FIXTURE = json.loads((EVALS / "fixtures" / "hybrid_catalogue.json").read_text(encoding="utf-8"))
BY_ID = {p["id"]: p for p in FIXTURE}


def attr(key, value, source="staff_approved"):
    return SimpleNamespace(key=key, value=value, source=source)


def test_product_snapshot_is_byte_identical_and_hash_stable():
    r = product_representation("Brown  Pashmina Stole", "Stoles", "Pure pashmina", "Soft hand-woven stole.\n\nIdeal for  winter.",
                               [attr("season", "Winter"), attr("fabric", "pashmina"), attr("fabric", "Pashmina", "imported")])
    expected = ("type: product\nname: brown pashmina stole\ncategory: stoles\nmaterial: pure pashmina\n"
                "description: soft hand-woven stole. ideal for winter.\nattr.fabric: pashmina\nattr.season: winter")
    assert r.text == expected and r.version == "catalog-text-v1" == REPRESENTATION_VERSION and r.kind == "product"
    assert r.sha256 == hashlib.sha256(f"catalog-text-v1\n{expected}".encode()).hexdigest()
    assert r.sha256 == "5fe7f1897422982583893bd15c8dd6b0bc0707a34f76b7cae2be9af14363fcb1"  # pinned: change = re-embed (S4b)
    assert product_representation("Brown Pashmina Stole", "stoles", "pure pashmina", "Soft hand-woven stole. Ideal for winter.",
                                  [attr("fabric", "pashmina"), attr("season", "winter")]) == r


def test_variant_snapshot_and_product_variant_are_distinct_and_identity_independent():
    v = variant_representation("Brown Pashmina Stole", "Camel", "Camel", "stoles", "Pure pashmina", [attr("color_name", "camel", "imported")])
    assert v.text == ("type: variant\nproduct: brown pashmina stole\ncategory: stoles\nmaterial: pure pashmina\n"
                      "variant: camel\ncolor: camel\nattr.color_name: camel")
    p = product_representation("Brown Pashmina Stole", "stoles", "Pure pashmina")
    assert v.kind == "variant" and v.text != p.text and v.sha256 != p.sha256
    assert variant_representation("Brown Pashmina Stole", "Camel", "Camel", "stoles", "Pure pashmina",
                                  [attr("color_name", "camel", "imported")]) == v  # no id anywhere: same fields, same text


def test_urdu_roman_urdu_and_unicode_normalisation():
    assert clean("بھوری‌  شَال ۴۰۰۰") == clean("بھوری شال 4000") == "بھوری شال 4000"
    assert clean("كالا") == clean("کالا")  # Arabic kaf/yeh folded like catalog.query
    assert clean("ＳＨＡＷＬ  Chadar\t\n") == "shawl chadar"
    urdu = product_representation("بھورا پشمینہ شال", "shawls", "خالص پشمینہ").text
    assert urdu == "type: product\nname: بھورا پشمینہ شال\ncategory: shawls\nmaterial: خالص پشمینہ"
    assert "sardi ke liye garam" in product_representation("Kali Oon Chadar", description="Sardi ke liye   GARAM").text


def test_missing_fields_are_omitted_and_unapproved_or_empty_attributes_ignored():
    r = product_representation("Wrap", None, "  ", None, [attr("fabric", None), attr("style", "floral", "visual_suggestion"),
                                                           attr("season", "   ")])
    assert r.text == "type: product\nname: wrap"
    with pytest.raises(ValueError):
        product_representation("   ")
    with pytest.raises(ValueError):
        variant_representation("")
    with pytest.raises(ValueError):
        product_representation("x", attributes=[attr("price", "10")])


def test_repeated_attributes_are_deduplicated_sorted_and_input_order_independent():
    rows = [attr("occasion", "wedding", "supplier_declared"), attr("occasion", "Daily Wear"), attr("occasion", "wedding", "imported")]
    a = product_representation("X", attributes=rows)
    assert a.text.endswith("attr.occasion: daily wear; wedding")
    assert product_representation("X", attributes=list(reversed(rows))) == a


def test_overflow_fails_visibly_at_the_limit_and_never_truncates():
    base = len(product_representation("x", description="a").text)
    ok = product_representation("x", description="a" * (rep.MAX_CHARS - base + 1))
    assert len(ok.text) == rep.MAX_CHARS
    with pytest.raises(RepresentationTooLong):
        product_representation("x", description="a" * (rep.MAX_CHARS - base + 2))


def test_version_is_part_of_the_hash(monkeypatch):
    before = product_representation("x").sha256
    monkeypatch.setattr(rep, "REPRESENTATION_VERSION", "catalog-text-v2")
    after = product_representation("x")
    assert after.version == "catalog-text-v2" and after.sha256 != before


@pytest.mark.parametrize("product", FIXTURE, ids=lambda p: p["id"])
def test_private_price_stock_and_ids_never_enter_text(product):
    texts = hybrid.representations(product)
    assert len(texts) == 1 + len(product["variants"])
    for text in texts:
        assert hybrid.leaks(product, text) == []
        for banned in ("price", "stock", "pkr", "http", "sku", "created", "updated", "customer", "supplier cost", "paisley"):
            assert banned not in text


def test_leak_detector_actually_detects():
    product = BY_ID["h01"]
    assert hybrid.leaks(product, "name: x\nnote: supplier cost 1200, call ahmed 0300-0000000") != []
    assert "3500" in hybrid.leaks(product, "priced 3500 today")
    assert hybrid.leaks(product, "ten 10 items") == []  # whole-word numbers: "0" in "10" is not a leak


def test_fixture_covers_the_required_cases():
    assert {p["status"] for p in FIXTURE} >= {"active", "draft", "archived"} and len({p["scope"] for p in FIXTURE}) == 2
    assert any(len(p["variants"]) > 2 for p in FIXTURE)
    assert any(p["material"] is None or p["description"] is None for p in FIXTURE)
    assert any(v["color"] is None for p in FIXTURE for v in p["variants"])
    assert any(v["stock"] == 0 for p in FIXTURE for v in p["variants"]) and any(v["price"] == 1800 for p in FIXTURE for v in p["variants"])
    assert {p["name"] for p in FIXTURE if p["scope"] == "store-b"} <= {p["name"] for p in FIXTURE if p["scope"] == "store-a"}


def test_eval_loader_is_non_empty_and_semantic_metrics_are_not_evaluated(tmp_path, capsys):
    cases = [json.loads(line) for line in (EVALS / "datasets" / "retrieval_hybrid.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert len(cases) >= 6 and {c["lang"] for c in cases} == {"en", "ur", "roman_ur"}
    out = tmp_path / "out.json"
    assert hybrid.main(["--json", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["fixture_integrity"] == "pass" and result["release_ready"] is False
    assert result["semantic_metrics"] == {"recall_at_10": None, "mrr": None, "status": "NOT_EVALUATED"}
    assert "semantic_metrics=NOT_EVALUATED" in capsys.readouterr().out


def test_eval_runner_fails_empty_dataset_and_bad_ids(tmp_path, capsys):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets" / "retrieval_hybrid.jsonl").write_text("\n", encoding="utf-8")
    assert hybrid.main(["--root", str(tmp_path)]) == 2 and "NOT_EVALUATED" in capsys.readouterr().out
    bad = [{"id": "b", "lang": "en", "relevant_ids": ["d01"], "decoy_ids": ["h01"]}]
    assert len(hybrid.check(bad, FIXTURE)) >= 3  # draft relevant, eligible decoy, missing languages


def test_existing_s1_retrieval_gate_is_unchanged_and_green():
    done = subprocess.run([sys.executable, str(EVALS / "run_retrieval_evals.py")], capture_output=True, text=True)
    assert done.returncode == 0 and "PASS" in done.stdout
