"""Deterministic query parser: filters, aliases, currency, review/clarification paths and hard-filter handoff."""
import pytest

from repositories.products import VariantFilter
from semantic.query_parser import QUESTIONS, handoff, normalize_query, parse_query
from utils.colour_vocabulary import CANONICAL


def ok(q, **want):
    i = parse_query(q)
    assert not i.needs_review, i.reasons
    for k, v in want.items():
        assert getattr(i, k) == v, k
    return i


@pytest.mark.parametrize("q,want", [
    ("brown stole under 4000", dict(colour="brown", max_price=4000, currency="PKR", terms=("stole",))),
    ("in stock scarves under 2,500", dict(in_stock=True, max_price=2500, terms=("scarf",))),
    ("pashmina shawl between 5000 and 9000", dict(min_price=5000, max_price=9000, terms=("pashmina", "shawl"))),
    ("stole above 3k rs", dict(min_price=3000, currency="PKR")),
    ("from 5000 to rs 9000", dict(min_price=5000, max_price=9000)),
    ("5000-9000 rupees", dict(min_price=5000, max_price=9000)),
    ("Gray   shawl", dict(colour="grey", terms=("shawl",))),
    ("navy blue stole", dict(colour="navy", terms=("stole",))),
    ("off-white", dict(colour="ivory")),
    ("available shawls", dict(in_stock=True)),
    ("show me everything", dict(colour=None, terms=())),
])
def test_english_filters(q, want):
    ok(q, **want)


@pytest.mark.parametrize("q,lang,want", [
    ("bhoora shawal 4000 se kam", "roman_ur", dict(colour="brown", max_price=4000, terms=("shawl",))),
    ("4500 se zyada ka scarf", "roman_ur", dict(min_price=4500, terms=("scarf",))),
    ("safaid stole", "roman_ur", dict(colour="white")),
    ("بھورا شال ۴۰۰۰ سے کم", "ur", dict(colour="brown", max_price=4000, terms=("shawl",))),
    ("کریم رنگ کی شال", "ur", dict(colour="cream")),
])
def test_urdu_and_roman_urdu_use_only_the_controlled_vocabulary(q, lang, want):
    assert ok(q, **want).language == lang


def test_every_canonical_colour_parses_to_itself():
    for c in CANONICAL:
        assert ok(c).colour == c


@pytest.mark.parametrize("q,reason", [
    ("", "empty_query"), ("   ", "empty_query"),
    ("x " * 101, "query_too_long"),
    ("alpha beta gamma delta epsilon zeta eta theta iota", "too_many_terms"),
    ("你好 shawl", "unsupported_language"), ("خوبصورت شال", "unsupported_language"),
    ("shawl not black", "negation_unsupported"), ("gulabi shawl, white nahi", "negation_unsupported"),
    ("grey or beige stole", "ambiguous_colour"),
    ("$50 shawl under 50 dollars", "unsupported_currency"),
    ("under 5000 usd", "unsupported_currency"),
    ("under 4,00,0", "malformed_number"), ("under 1.2.3", "malformed_number"), ("under 12abc", "malformed_number"),
    ("under 2500.5", "malformed_number"), ("under 99999999999", "malformed_number"),
    ("stole 4000", "ambiguous_number"),
    ("under", "dangling_comparator"), ("4000 se kam se kam", "dangling_comparator"),
    ("red under 3000 under 5000", "contradictory_price"), ("under 5000 over 6000", "contradictory_price"),
    ("between 9000 and 5000", "contradictory_price"),
    ("in stock and sold out", "contradictory_stock"),
    ("red sold out", "unsupported_stock_filter"),
])
def test_unresolvable_queries_ask_instead_of_guessing(q, reason):
    i = parse_query(q)
    assert i.needs_review and reason in i.reasons
    assert QUESTIONS[reason] in i.clarifications and len(i.clarifications) == len(i.reasons)
    assert handoff(i) is None


def test_mixed_currency_is_reviewed_and_not_converted():
    i = parse_query("under rs 5000 or 40 usd")
    assert i.needs_review and "mixed_currency" in i.reasons and i.currency is None
    assert handoff(i) is None


def test_default_and_stated_currency_provenance():
    assert [p.rule for p in ok("under 100").provenance if p.field == "currency"] == ["default"]
    assert [p.rule for p in ok("under pkr 100").provenance if p.field == "currency"] == ["stated"]


def test_provenance_records_source_text_and_rule():
    prov = {(p.field, p.value): (p.text, p.rule) for p in ok("gulabi shawl 4000 se kam").provenance}
    assert prov[("colour", "pink")] == ("gulabi", "alias")
    assert prov[("max_price", "4000")] == ("4000 se kam", "comparator")
    assert prov[("term", "shawl")][1] == "term"


def test_deterministic_and_normalised():
    a, b = parse_query("  Brown   STOLE  Under ۴۰۰۰ "), parse_query("brown stole under 4000")
    assert a.normalized == b.normalized and (a.colour, a.max_price, a.terms, a.provenance) == (b.colour, b.max_price, b.terms, b.provenance)
    assert parse_query("brown stole under 4000") == b
    assert normalize_query("ＢＬＡＣＫ،") == "black,"
    assert parse_query(None).reasons == ("empty_query",)


def test_handoff_maps_to_single_variant_hard_filter():
    h = handoff(parse_query("in stock brown stole between 1000 and 4000"))
    assert h.q == "stole"
    assert h.variant == VariantFilter("brown", 1000, 4000, True)
    assert handoff(parse_query("stole")).variant is None
    assert handoff(parse_query("show me everything")).q is None
