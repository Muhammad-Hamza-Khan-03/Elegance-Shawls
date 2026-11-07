"""Findings from the first real WhatsApp run: chat filler must not become a product word, and a bare "?" must not resurrect an old search."""
import pytest

from assistant import conversation
from semantic.query_parser import handoff, parse_query


@pytest.mark.parametrize("text", ["One black shawl", "one black shawl please", "i want a black shawl", "Hello, black shawl", "Kaali shawl"])
def test_quantity_and_greeting_words_do_not_block_a_colour_and_product_search(text):
    plan = handoff(parse_query(text))
    assert plan.q == "shawl" and plan.variant.colour == "black"


@pytest.mark.parametrize("text", ["?", "Hi", "hello", "thanks", "ok"])
def test_greetings_state_nothing_to_search(text):
    assert handoff(parse_query(text)).q is None


@pytest.mark.parametrize("text", ["?", "Hi", "thanks"])
def test_a_bare_message_does_not_carry_the_previous_search(text):
    effective, kept = conversation.with_history(["grey shawls under 6000"], text, parse_query(text))
    assert kept == [] and handoff(effective).q is None


def test_a_real_follow_up_still_carries():
    effective, kept = conversation.with_history(["grey shawls"], "under 3000", parse_query("under 3000"))
    assert kept and handoff(effective).variant.colour == "grey" and handoff(effective).variant.max_price == 3000
