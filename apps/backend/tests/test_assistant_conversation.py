import pytest

from assistant.conversation import with_history
from semantic.query_parser import parse_query


def ask(*messages):
    """Fold a whole conversation like the server does: earlier messages are history, the last is current."""
    *history, last = messages
    intent, kept = with_history(history, last, parse_query(last))
    return intent, kept


def test_the_reported_conversation_keeps_colour_and_product_type_across_follow_ups():
    first, _ = ask("show me shawls of grey under 2000")
    assert (first.colour, first.max_price, first.terms) == ("grey", 2000, ("shawl",))
    second, kept = ask("show me shawls of grey under 2000", "under 3000")
    assert (second.colour, second.max_price, second.terms) == ("grey", 3000, ("shawl",))          # budget replaced, the rest kept
    assert "colour grey" in kept and "shawl" in kept and not any("2000" in k for k in kept)
    third, _ = ask("show me shawls of grey under 2000", "under 3000", "grey color")
    assert (third.colour, third.max_price, third.terms) == ("grey", 3000, ("shawl",))            # "grey color" alone changes nothing


def test_a_new_statement_overrides_only_what_it_states():
    colour, _ = ask("red shawl under 3000", "blue")
    assert (colour.colour, colour.max_price, colour.terms) == ("blue", 3000, ("shawl",))
    kind, _ = ask("red shawl under 3000", "what about stoles")
    assert (kind.colour, kind.max_price, kind.terms) == ("red", 3000, ("stole",))
    stock, _ = ask("brown shawls", "in stock")
    assert (stock.colour, stock.terms, stock.in_stock) == ("brown", ("shawl",), True)


def test_a_contradicting_budget_does_not_leave_an_impossible_range():
    cheaper, _ = ask("shawl over 5000", "under 3000")
    assert cheaper.max_price == 3000 and cheaper.min_price is None
    dearer, _ = ask("shawl under 3000", "over 5000")
    assert dearer.min_price == 5000 and dearer.max_price is None


@pytest.mark.parametrize("fresh", ["delivery kitne din mein hoti hai", "hello", "iphone ki price"])
def test_an_unrelated_message_starts_fresh_and_inherits_nothing(fresh):
    intent, kept = ask("grey shawl under 2000", fresh)
    assert kept == [] and intent.colour is None and intent.max_price is None


def test_a_message_the_parser_had_to_question_contributes_nothing_and_asks_again():
    intent, kept = ask("grey shawl under 2000", "not red")                     # negation: needs clarification, never a guess
    assert intent.needs_review and kept == []
    after, _ = ask("grey shawl under 2000", "not red", "under 3000")
    assert (after.colour, after.max_price) == ("grey", 3000)                    # the questioned message was skipped


def test_history_is_bounded_untrusted_text_and_cannot_break_the_parser():
    junk = ["x" * 5000, "', DROP TABLE", "\u0000", 42, None]
    intent, kept = with_history(junk, "under 3000", parse_query("under 3000"))   # type: ignore[arg-type]
    assert intent.max_price == 3000
    old, _ = ask("red shawl", "blue shawl", "green shawl", "pink shawl", "under 3000")
    assert old.colour == "pink"                                                  # only the last three messages count


def test_roman_urdu_follow_ups_work_the_same_way():
    intent, kept = ask("kaali chaadar 5000 se kam", "3000 se kam")
    assert (intent.colour, intent.max_price, intent.terms) == ("black", 3000, ("shawl",))
