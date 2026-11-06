"""Container-free: every row of the reply table, parsing, rendering."""
from datetime import datetime, timedelta, timezone

from whatsapp import replies
from whatsapp.replies import Decision, Facts, decide, parse_details, render

NOW = datetime(2026, 11, 6, 14, 0, tzinfo=timezone.utc)
ITEMS = [{"product": "Wool Shawl", "color": "Red", "size": "Free", "quantity": 2, "unit_price": 4500, "variant_id": "v1"}]


def facts(**over):
    base = dict(now=NOW, event_ts=NOW, text="hi", max_age=timedelta(minutes=15), allowlisted=True, paused=False, bot_recent=False,
                reference_in_message=False, has_enquiry=True, summary_sent=False)
    return Facts(**{**base, **over})


def test_first_reference_message_gets_summary_asking_only_for_missing_details():
    d = decide(facts(reference_in_message=True, details={"name": "Ayesha"}))
    assert d == Decision("summary", missing=("city", "address"))
    text = render(d, lang="en", reference="ES-ABCDEF", items=ITEMS, total=9000, currency="PKR")
    assert "1. Wool Shawl (Red / Free) x 2 = PKR 9,000" in text and "Total: PKR 9,000" in text
    assert "City:" in text and "Address:" in text and "Name:" not in text
    assert "confirmed" not in text.lower().replace("will confirm", "")


def test_complete_details_skip_the_question():
    d = decide(facts(reference_in_message=True, details={"name": "A", "city": "B", "address": "C"}))
    assert "Name:" not in render(d, lang="en", reference="ES-X", items=ITEMS, total=9000, currency="PKR")


def test_price_or_stock_change_states_it_confirms_nothing_and_flags():
    issues = ({"variant_id": "v1", "reason": "price_changed", "current_price": 5000, "current_currency": "PKR"},)
    d = decide(facts(reference_in_message=True, issues=issues))
    assert d.kind == "changed" and d.flag
    text = render(d, lang="en", reference="ES-X", items=ITEMS, total=9000, currency="PKR", issues=issues)
    assert "price is now PKR 5,000" in text and "Nothing is confirmed" in text


def test_details_are_saved_then_acknowledged_once():
    d = decide(facts(summary_sent=True, text="Name: Ayesha\nCity: Lahore\nAddress: 12 Mall Road", details={}))
    assert d == Decision("details_done", save_details={"name": "Ayesha", "city": "Lahore", "address": "12 Mall Road"})
    assert decide(facts(summary_sent=True, text="Name: Ayesha", details={"name": "A", "city": "B", "address": "C"})) is None
    part = decide(facts(summary_sent=True, text="City: Lahore", details={"name": "A"}))
    assert part.kind == "ask_missing" and part.missing == ("address",)


def test_unknown_or_missing_reference_asks_once():
    assert decide(facts(has_enquiry=False)).kind == "need_reference"
    assert decide(facts(has_enquiry=False, bot_recent=True)) is None


def test_anything_else_gets_one_holding_reply_per_window():
    assert decide(facts(summary_sent=True, text="is it pure wool?")).kind == "holding"
    assert decide(facts(summary_sent=True, text=None, bot_recent=True)) is None
    assert decide(facts(text=None)).kind == "holding"


def test_silent_when_staff_active_off_allowlist_or_message_is_stale():
    assert decide(facts(reference_in_message=True, paused=True)) is None
    assert decide(facts(reference_in_message=True, allowlisted=False)) is None
    assert decide(facts(reference_in_message=True, event_ts=NOW - timedelta(hours=1))) is None


def test_parse_details_english_and_urdu_labels_with_limits():
    assert parse_details("name - Ali\ncity: Karachi") == {"name": "Ali", "city": "Karachi"}
    assert parse_details("نام: علی\nشہر: لاہور") == {"name": "علی", "city": "لاہور"}
    assert len(parse_details("Address: " + "x" * 999)["address"]) == 300
    assert parse_details("just chatting") == {}


def test_urdu_customers_get_urdu_templates():
    assert replies.language("السلام علیکم") == "ur" and replies.language("hello") == "en"
    assert render(Decision("holding"), lang="ur", reference="", items=[], total=0, currency="PKR").startswith("آپ")


def test_templates_have_the_same_keys_in_both_languages():
    t = replies._templates()
    assert t["en"].keys() == t["ur"].keys()
