import pytest

from assistant.personal import Preferences, is_recall, rank, recall_text, remember_request, taste_offer


@pytest.mark.parametrize("text,expected", [
    ("remember I like brown", [{"key": "favourite_colour", "value": "brown"}]),
    ("yaad rakho mujhe kala pasand hai", [{"key": "favourite_colour", "value": "black"}]),
    ("remember my budget is under 4000", [{"key": "budget_max_pkr", "value": "4000"}]),
    ("remember I like brown, under 4000", [{"key": "favourite_colour", "value": "brown"}, {"key": "budget_max_pkr", "value": "4000"}]),
    ("please remember this", []),
])
def test_explicit_remember_requests_are_parsed_deterministically(text, expected):
    assert remember_request(text) == expected


@pytest.mark.parametrize("text", ["I like brown", "brown shawl under 4000", "mujhe kala pasand hai", "do not forget", "show me a shawl"])
def test_taste_or_search_without_an_explicit_remember_is_not_a_memory_request(text):
    assert remember_request(text) is None


ON = Preferences("on", {})


@pytest.mark.parametrize("text,keys", [("I like pink", {"favourite_colour"}), ("I like shawls", {"preferred_category"}), ("mujhe kala pasand hai", {"favourite_colour"}),
                                        ("i love green stoles", {"favourite_colour", "preferred_category"}), ("I prefer scarves under 3000", {"preferred_category", "budget_max_pkr"})])
def test_a_stated_taste_yields_offers_only_when_opted_in(text, keys):
    assert {o["key"] for o in taste_offer(text, ON)} == keys
    assert taste_offer(text, Preferences("off", {})) == [] and taste_offer(text, Preferences("anonymous", {})) == []


@pytest.mark.parametrize("text", ["pink shawl dikhao", "show me green stoles", "what do I like", "hello"])
def test_searches_and_questions_are_not_offered(text):
    assert taste_offer(text, ON) == []


@pytest.mark.parametrize("text", ["what do I like?", "which items are my fav?", "what have you saved", "mujhe kya pasand hai", "mere pasand kya hai", "what do you remember about me"])
def test_recall_questions_are_recognised(text):
    assert is_recall(text)


@pytest.mark.parametrize("text", ["I like pink", "show me shawls", "remember I like brown"])
def test_other_messages_are_not_recall(text):
    assert not is_recall(text)


def test_recall_text_covers_every_state():
    assert "sign in" in recall_text(Preferences("anonymous", {}))
    assert "off" in recall_text(Preferences("off", {}))
    assert "not saved anything" in recall_text(ON)
    both = recall_text(Preferences("on", {}, (("cloth", "pashmina"), ("favourite_colour", "pink"))))
    assert "cloth: pashmina" in both and "favourite colour: pink" in both


def product(name, *variants):
    return {"name": name, "variants": [{"is_active": True, "stock": 2, "price": p, "color": c} for c, p in variants]}


def test_rank_is_stable_never_drops_results_and_reports_what_it_applied():
    items = [product("a", ("Red", 5000)), product("b", ("Brown", 5000)), product("c", ("Brown", 1000))]
    ordered, applied = rank(items, Preferences("on", {"favourite_colour": "brown", "budget_max_pkr": "2000"}), colour_in_query=False)
    assert [p["name"] for p in ordered] == ["c", "b", "a"] and len(ordered) == 3
    assert applied == ["favourite colour brown", "budget up to PKR 2000"]
    plain, none = rank(items, Preferences("on", {"favourite_colour": "brown"}), colour_in_query=True)
    assert [p["name"] for p in plain] == ["a", "b", "c"] and none == []


def test_garbage_preferences_are_ignored():
    items = [product("a", ("Red", 1)), product("b", ("Brown", 1))]
    for bad in ({"budget_max_pkr": "lots"}, {"budget_max_pkr": "-5"}, {"favourite_colour": "not-a-colour"}):
        ordered, applied = rank(items, Preferences("on", bad), colour_in_query=False)
        assert [p["name"] for p in ordered] == ["a", "b"] and applied == []
