"""Enrichment output contract: strict schema, canonical vocabulary, prohibited fields, sanitising. No network."""
import json

import pytest

from enrichment.contract import FIELDS, FREE_TEXT, PROHIBITED, SOURCE, allowed_values, input_hash, parse_response, sanitize

SOURCE_TEXT = "Sample Ivory Stole A light stole with a floral border"


def ok(value, reason=None):
    return {"value": value, "reason": reason}


def valid() -> dict:
    data = {f: ok(sorted(allowed_values(f))[0]) for f in FIELDS if f not in FREE_TEXT}
    data["color_name"] = ok("cream")
    data["description"] = ok("A light stole with a floral border.")
    data["seo_title"] = ok("Ivory floral stole")
    data["seo_description"] = ok("A light ivory stole with a floral border for winter evenings.")
    return data


def parse(data, source=SOURCE_TEXT):
    return parse_response(data if isinstance(data, str) else json.dumps(data), source)


def test_valid_response_is_accepted_and_tagged_as_a_visual_suggestion():
    parsed = parse(valid())
    assert parsed.errors == [] and set(parsed.suggestions) == set(FIELDS)
    assert all(entry["source"] == SOURCE for entry in parsed.suggestions.values())


def test_json_in_a_code_fence_is_accepted():
    assert parse("```json\n" + json.dumps(valid()) + "\n```").errors == []


@pytest.mark.parametrize("raw", ["not json", "[]", '"text"', "", "{"])
def test_malformed_or_non_object_json_is_rejected(raw):
    parsed = parse_response(raw, SOURCE_TEXT)
    assert parsed.suggestions is None and parsed.errors


@pytest.mark.parametrize("extra", ["fabric", "composition", "authenticity", "price", "stock", "availability", "sku", "anything"])
def test_extra_and_factual_fields_are_rejected(extra):
    parsed = parse({**valid(), extra: ok("x")})
    assert parsed.suggestions is None and any("unexpected" in e for e in parsed.errors)
    assert any("prohibited" in e for e in parsed.errors) == (extra in PROHIBITED)


def test_missing_field_is_rejected():
    data = valid()
    del data["style"]
    assert parse(data).suggestions is None


@pytest.mark.parametrize("entry", ["cream", {"value": "cream"}, {"value": "cream", "reason": None, "extra": 1}, ok(5), ok(["a"])])
def test_field_shape_is_strict(entry):
    assert parse({**valid(), "color_name": entry}).suggestions is None


@pytest.mark.parametrize("field,value", [("color_name", "teal-ish"), ("color_family", "Warm"), ("pattern", "tartan"),
                                         ("occasion", "funeral"), ("season", "monsoon"), ("style", "cool")])
def test_out_of_vocabulary_values_are_rejected(field, value):
    parsed = parse({**valid(), field: ok(value)})
    assert parsed.suggestions is None and any("vocabulary" in e for e in parsed.errors)


def test_color_name_uses_the_catalogue_colour_vocabulary():
    assert {"black", "cream", "navy"} <= allowed_values("color_name")


def test_unknown_must_be_null_with_a_reason():
    parsed = parse({**valid(), "occasion": ok(None, "ambiguous: text mentions weddings and travel")})
    assert parsed.errors == [] and parsed.suggestions["occasion"]["value"] is None
    assert parse({**valid(), "occasion": ok(None)}).suggestions is None
    assert parse({**valid(), "occasion": ok(None, "")}).suggestions is None


def test_free_text_is_stripped_of_markup_and_capped():
    long = "word " * 400
    data = {**valid(), "description": ok("<b>Soft</b>\x00 and\n light <script>x</script>"), "seo_title": ok(long)}
    out = parse(data).suggestions
    assert "<" not in out["description"]["value"] and "\x00" not in out["description"]["value"]
    assert len(out["seo_title"]["value"]) <= FREE_TEXT["seo_title"]
    assert out["seo_title"]["value"].endswith("word")


def test_sanitize_collapses_whitespace_and_caps_at_a_word():
    assert sanitize("  a \n\t b  ", 50) == "a b"
    assert sanitize("alpha beta gamma", 12) == "alpha beta"


@pytest.mark.parametrize("claim", ["100% pure wool", "Only Rs 4000 today", "Genuine pashmina", "Now in stock", "Priced to sell",
                                   "Handmade in Kashmir", "50% off sale", "just $20"])
def test_factual_claims_in_free_text_are_rejected(claim):
    parsed = parse({**valid(), "description": ok(claim)})
    assert parsed.suggestions is None and any("factual claim" in e for e in parsed.errors)


def test_fabric_not_present_in_the_source_is_rejected_but_source_fabric_is_allowed():
    data = {**valid(), "seo_description": ok("A soft cashmere stole.")}
    assert parse(data, SOURCE_TEXT).suggestions is None
    assert parse(data, "Stole made of cashmere").errors == []


def test_errors_never_echo_model_output():
    secret = "SECRET-MODEL-OUTPUT"
    parsed = parse({**valid(), "pattern": ok(secret), "extra_" + secret: ok(secret), "style": ok(None, None)})
    assert parsed.errors and not any(secret in e for e in parsed.errors)


def test_input_hash_is_stable_and_input_sensitive():
    assert input_hash({"a": 1, "b": 2}) == input_hash({"b": 2, "a": 1})
    assert input_hash({"a": 1}) != input_hash({"a": 2})
