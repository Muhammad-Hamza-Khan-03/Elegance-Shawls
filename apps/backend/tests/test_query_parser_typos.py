import pytest

from semantic.query_parser import has_shopping_signal, parse_query


@pytest.mark.parametrize("typed,term", [("mufflar", "scarf"), ("embrodiered shawl", "embroidered"), ("silk skarff", "scarf"),
                                        ("scraf dikhao", "scarf"), ("wintr shawl", "winter"), ("shwal", "shawl"), ("red muflar", "scarf")])
def test_product_fabric_and_season_misspellings_become_the_intended_term(typed, term):
    intent = parse_query(typed)
    assert term in intent.terms and not intent.needs_review and has_shopping_signal(typed)


def test_a_misspelt_colour_is_never_turned_into_a_filter():
    for typed in ("blak shawl", "reed shawl", "brwn stole"):
        assert parse_query(typed).colour is None


@pytest.mark.parametrize("text", ["thank you", "hello", "iphone ki price", "delivery kitne din", "cricket score", "weather in lahore"])
def test_off_topic_text_has_no_shopping_signal(text):
    assert not has_shopping_signal(text)


def test_roman_urdu_and_urdu_season_words_reach_the_search_as_english_terms():
    assert parse_query("kuch halka chahiye garmi ke liye").terms == ("light", "summer")
    assert parse_query("کچھ گرم چاہیے").terms == ("warm",) and not parse_query("کچھ گرم چاہیے").needs_review
    assert parse_query("kaali chaadar").colour == "black" and "shawl" in parse_query("kaali chaadar").terms


def test_plural_product_words_become_the_singular_the_keyword_half_can_match():
    for plural, singular in (("shawls", "shawl"), ("stoles", "stole"), ("scarves", "scarf")):
        assert parse_query(f"pink {plural}").terms == (singular,)
    assert parse_query("I like pink shawls").terms == ("shawl",)       # "like" is filler, not a search word
