import pytest

from assistant.personal import Preferences, rank, remember_request


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
