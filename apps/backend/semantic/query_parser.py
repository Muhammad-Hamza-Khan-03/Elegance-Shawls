"""Deterministic natural-language query parser: text -> structured intent. No I/O, no model, no network.

Only what the hybrid search can enforce becomes a hard filter (one colour, a PKR price range, in-stock: the
`VariantFilter` that must hold on ONE variant). Everything else is a search term. Anything the parser cannot
resolve without guessing (negation, several colours, foreign currency, malformed or bare numbers, contradictions,
unrecognised Urdu-script or other-script words, over-long input) sets `needs_review` with a reason code and a
clarification question, and `handoff()` then returns None: a half-understood query never runs as a filtered search.
Bump PARSER_VERSION on any change to the tables or rules below.
(shortcut: small controlled Roman Urdu / Urdu lexicon and English clarifications only; grow it from the labelled
filter_parsing eval set, never by guessing.)
"""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from repositories.products import VariantFilter
from utils.colour_vocabulary import CANONICAL, SYNONYMS, VOCABULARY_VERSION

PARSER_VERSION = 1
MAX_QUERY_CHARS = 200
MAX_TERMS = 8  # same bound hybrid_search applies; more would be silently dropped there
MAX_PRICE = 2_147_483_647  # variants.price is a 32-bit integer (whole PKR)

# Parser-owned aliases (vocabulary_version stays untouched). Roman Urdu spellings and Urdu script.
LOCAL_COLOURS = {
    "bhoora": "brown", "bhura": "brown", "بھورا": "brown", "safaid": "white", "safed": "white", "سفید": "white",
    "kala": "black", "kaala": "black", "کالا": "black", "gulabi": "pink", "گلابی": "pink", "neela": "blue", "نیلا": "blue",
    "lal": "red", "surkh": "red", "لال": "red", "hara": "green", "سبز": "green", "peela": "yellow", "پیلا": "yellow",
    "kreem": "cream", "کریم": "cream", "narangi": "orange", "نارنجی": "orange",
}
CURRENCIES = {  # token -> ISO code; only PKR is supported (variant prices are PKR, no conversion is ever guessed)
    "rs": "PKR", "pkr": "PKR", "rupee": "PKR", "rupees": "PKR", "rupay": "PKR", "rupaye": "PKR", "₨": "PKR", "روپے": "PKR",
    "روپیہ": "PKR", "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD", "€": "EUR", "eur": "EUR", "euro": "EUR",
    "euros": "EUR", "£": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP", "₹": "INR", "inr": "INR",
}
PRE_MAX = ["under", "below", "upto", "up to", "less than", "max", "maximum", "within", "cheaper than", "<"]
PRE_MIN = ["over", "above", "more than", "at least", "min", "minimum", "from", "greater than", ">"]
POST_MAX = ["se kam", "say kam", "tak", "سے کم", "تک", "or less", "or under", "or below"]
POST_MIN = ["se zyada", "se ziada", "se upar", "say zyada", "سے زیادہ", "سے اوپر", "or more", "or above", "and above"]
STOCK_IN = ["in stock", "available", "stock mein", "dastiyab", "دستیاب", "موجود"]
STOCK_OUT = ["out of stock", "sold out", "unavailable", "stock khatam"]
NEGATION = ["not", "no", "without", "except", "excluding", "nahi", "nahin", "bagair", "بغیر", "نہیں", "نہ"]
ALIASES = {"shawal": "shawl", "shal": "shawl", "شال": "shawl", "اسٹول": "stole"}  # term spellings only, no category filter
FILLER = set("or a an the in of for some something any and with me show everything all i want need looking find please "
             "colour color rang ka ki ke se say ko mein hai کا کی کے رنگ سے میں".split())
ROMAN_URDU = {w for w in LOCAL_COLOURS if w.isascii()} | {"se kam", "say kam", "tak", "se zyada", "se ziada", "se upar",
              "say zyada", "stock mein", "dastiyab", "nahi", "nahin", "bagair", "rupay", "rupaye", "stock khatam",
              "shawal", "shal", "rang", "ka", "ki", "ke"}
RANGE_SEP = {"and", "to", "-"}

QUESTIONS = {
    "empty_query": "What are you looking for?",
    "query_too_long": "Please shorten the search to a few words.",
    "too_many_terms": "Please use fewer words; which are the most important?",
    "unsupported_language": "Some words are not in the supported vocabulary. Could you rephrase in English, or name colour and price?",
    "negation_unsupported": "Exclusions (not / without) cannot be applied as filters. Which colour or item do you want?",
    "ambiguous_colour": "Which one colour do you want?",
    "unsupported_currency": "Prices are in PKR. Please give the budget in rupees.",
    "mixed_currency": "Prices are in PKR. Please give the budget in rupees only.",
    "malformed_number": "I could not read that number. What is the price, in rupees?",
    "ambiguous_number": "Is that number a maximum price, a minimum price, or something else?",
    "dangling_comparator": "What number goes with that price limit?",
    "contradictory_price": "The price limits conflict. What range do you want?",
    "contradictory_stock": "Do you want items in stock or out of stock?",
    "unsupported_stock_filter": "Only in-stock filtering is available. Do you want items that are in stock?",
}


@dataclass(frozen=True)
class Provenance:
    field: str  # colour | min_price | max_price | currency | in_stock | term
    value: str
    text: str  # normalized source words
    rule: str


@dataclass(frozen=True)
class QueryIntent:
    raw: str
    normalized: str
    language: str  # en | roman_ur | ur | mixed | unknown
    colour: str | None
    min_price: int | None
    max_price: int | None
    currency: str | None
    in_stock: bool
    terms: tuple[str, ...]
    needs_review: bool
    reasons: tuple[str, ...]
    clarifications: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    parser_version: int = PARSER_VERSION
    vocabulary_version: int = VOCABULARY_VERSION


@dataclass(frozen=True)
class Handoff:
    """Keyword arguments for `hybrid_search`: q is terms only, `variant` the single-variant hard filter."""
    q: str | None
    variant: VariantFilter | None


def _phrases(*groups: tuple[list[str], str]) -> dict[tuple[str, ...], str]:
    return {tuple(p.split()): kind for words, kind in groups for p in words}


_PHRASES = _phrases((PRE_MAX, "pre_max"), (PRE_MIN, "pre_min"), (STOCK_IN, "stock_in"), (STOCK_OUT, "stock_out"),
                    (NEGATION, "neg"), (["between"], "between"))
_POST = _phrases((POST_MAX, "max"), (POST_MIN, "min"))
_COLOURS = {tuple(k.split()): c for k, c in {**{c: c for c in CANONICAL}, **SYNONYMS, **LOCAL_COLOURS}.items()}
_TOKEN = re.compile(r"\d[\d.,]*[^\W\d_]*|[^\W\d_]+(?:[-'][^\W\d_]+)*|[$€£₨₹<>-]")
_NUMBER = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(k)?")
_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")} | {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}


def normalize_query(raw: str) -> str:
    """NFKC, casefold, Arabic-Indic digits to ASCII, Urdu comma to ','; single-spaced."""
    text = unicodedata.normalize("NFKC", raw).casefold().translate(_DIGITS).replace("،", ",")
    return " ".join(text.split())


def _number(token: str) -> int | None:
    """Whole PKR from '4000', '4,000', '4k', '1.5k'; None for anything malformed ('1.2.3', '4,00,0', '12abc', '2500.5')."""
    m = _NUMBER.fullmatch(token.rstrip(".,"))
    if not m:
        return None
    value = Decimal(m[1].replace(",", "") + ("." + m[2] if m[2] else "")) * (1000 if m[3] else 1)
    return int(value) if value == value.to_integral_value() and value <= MAX_PRICE else None


def _script(word: str) -> str:
    names = {unicodedata.name(c, "").split(" ")[0] for c in word if c.isalpha()}
    return "arabic" if "ARABIC" in names else "latin" if names <= {"LATIN"} else "other"


def parse_query(raw: str | None) -> QueryIntent:
    raw = raw or ""
    text = normalize_query(raw)
    flags: dict[str, None] = {}  # ordered set of reason codes
    prov: list[Provenance] = []
    colours: dict[str, str] = {}
    maxes: dict[int, str] = {}
    mins: dict[int, str] = {}
    currencies: dict[str, str] = {}
    stock = {"in": None, "out": None}
    terms: list[str] = []
    langs: set[str] = set()
    pending: tuple[str, str] | None = None

    def flag(code: str):
        flags.setdefault(code)

    def money(tokens: list[str], i: int) -> int:
        """Record currency tokens starting at i; return the index after them."""
        while i < len(tokens) and tokens[i] in CURRENCIES:
            currencies.setdefault(CURRENCIES[tokens[i]], tokens[i])
            if tokens[i] in ("rupay", "rupaye"):
                langs.add("roman_ur")
            elif not tokens[i].isascii():
                langs.add("ur")
            i += 1
        return i

    if not text:
        flag("empty_query")
    if len(text) > MAX_QUERY_CHARS:
        flag("query_too_long")
        tokens: list[str] = []  # never parse a truncated query
    else:
        tokens = _TOKEN.findall(text)
    i = 0
    while i < len(tokens):
        t = tokens[i]
        at = lambda n: tuple(tokens[i:i + n])  # noqa: E731
        if t[0].isdigit():
            first = _number(t)
            j = money(tokens, i + 1)
            if first is None:
                flag("malformed_number")
                i = j
                continue
            second = None
            nxt = j + 1
            while nxt < len(tokens) and tokens[nxt] in CURRENCIES:
                nxt += 1
            if (pending and pending[0] == "between") or (nxt < len(tokens) and tokens[j] in ("to", "-") and tokens[nxt][:1].isdigit()):
                if j < len(tokens) and tokens[j] in RANGE_SEP:
                    k = money(tokens, j + 1)
                    if k < len(tokens) and tokens[k][:1].isdigit():
                        second = _number(tokens[k])
                        if second is None:
                            flag("malformed_number")
                        j = money(tokens, k + 1)
                if second is not None:
                    lo, hi = first, second
                    if lo > hi:
                        flag("contradictory_price")
                    mins[lo] = maxes[hi] = " ".join(tokens[i:j])
                    prov.append(Provenance("min_price", str(lo), " ".join(tokens[i:j]), "range"))
                    prov.append(Provenance("max_price", str(hi), " ".join(tokens[i:j]), "range"))
                    pending, i = None, j
                    continue
                if pending:
                    flag("dangling_comparator")
            post = next(((_POST[p], len(p)) for n in (2, 1) if (p := tuple(tokens[j:j + n])) in _POST), None)
            kind = pending[0].removeprefix("pre_") if pending and pending[0] != "between" else post and post[0]
            if post and not pending:
                j += post[1]
            if kind is None:
                flag("ambiguous_number")
            else:
                (maxes if kind == "max" else mins)[first] = " ".join(tokens[i:j])
                prov.append(Provenance(f"{kind}_price", str(first), " ".join(tokens[i:j]), "comparator"))
            pending, i = None, j
            continue
        if t in CURRENCIES:
            i = money(tokens, i)
            continue
        for n in (3, 2, 1):
            key = at(n)
            if len(key) == n and key in _COLOURS:
                colours.setdefault(_COLOURS[key], " ".join(key))
                prov.append(Provenance("colour", _COLOURS[key], " ".join(key), "alias" if " ".join(key) not in CANONICAL else "canonical"))
                langs.add("roman_ur" if key[0].isascii() and key[0] in LOCAL_COLOURS else "ur" if key[0] in LOCAL_COLOURS else "en")
                i += n
                break
            kind = _PHRASES.get(key) if len(key) == n else None
            if kind is None:
                continue
            if kind == "neg":
                flag("negation_unsupported")
            elif kind == "stock_in":
                stock["in"] = " ".join(key)
                prov.append(Provenance("in_stock", "true", " ".join(key), "stock_term"))
            elif kind == "stock_out":
                stock["out"] = " ".join(key)
            else:
                if pending:
                    flag("dangling_comparator")
                pending = (kind, " ".join(key))
            if " ".join(key) in ROMAN_URDU:
                langs.add("roman_ur")
            i += n
            break
        else:
            if tuple(tokens[i:i + 2]) in _POST or (t,) in _POST:
                flag("dangling_comparator")
            elif t in FILLER:
                langs.add("roman_ur" if t in ROMAN_URDU else "ur" if not t.isascii() else "")
            elif t != "-":
                if pending:
                    flag("dangling_comparator")
                    pending = None
                word = ALIASES.get(t, t)
                if _script(t) == "latin":
                    if t in ALIASES:
                        langs.add("ur" if not t.isascii() else "roman_ur")
                    if word not in terms:
                        terms.append(word)
                elif word != t and word not in terms:
                    terms.append(word)
                    langs.add("ur")
                else:
                    flag("unsupported_language")
            i += 1
    if pending:
        flag("dangling_comparator")

    if len(terms) > MAX_TERMS:
        flag("too_many_terms")
    if len(colours) > 1:
        flag("ambiguous_colour")
    if stock["in"] and stock["out"]:
        flag("contradictory_stock")
    elif stock["out"]:
        flag("unsupported_stock_filter")
    if len(maxes) > 1 or len(mins) > 1 or (mins and maxes and max(mins) > min(maxes)):
        flag("contradictory_price")
    codes = set(currencies)
    if len(codes) > 1:
        flag("mixed_currency")
    elif codes - {"PKR"}:
        flag("unsupported_currency")
    priced = bool(mins or maxes)
    currency = (next(iter(codes)) if len(codes) == 1 else None) or ("PKR" if priced and not codes else None)
    if currency:
        prov.append(Provenance("currency", currency, currencies.get(currency, ""), "stated" if codes else "default"))
    prov.extend(Provenance("term", w, w, "term") for w in terms)

    nonen = langs & {"ur", "roman_ur"}
    language = "unknown" if not text or ("unsupported_language" in flags and not nonen) else "mixed" if len(nonen) > 1 else next(iter(nonen), "en")
    reasons = tuple(flags)
    return QueryIntent(
        raw=raw, normalized=text, language=language,
        colour=next(iter(colours)) if len(colours) == 1 else None,
        min_price=min(mins) if len(mins) == 1 else None, max_price=min(maxes) if len(maxes) == 1 else None,
        currency=currency, in_stock=bool(stock["in"]) and not stock["out"], terms=tuple(terms),
        needs_review=bool(reasons), reasons=reasons, clarifications=tuple(QUESTIONS[r] for r in reasons),
        provenance=tuple(prov))


def handoff(intent: QueryIntent) -> Handoff | None:
    """Hard-filter handoff to hybrid_search, or None when the intent needs review (clarify first, never filter on a guess)."""
    if intent.needs_review:
        return None
    variant = VariantFilter(intent.colour, intent.min_price, intent.max_price, intent.in_stock)
    has_filter = intent.colour or intent.min_price is not None or intent.max_price is not None or intent.in_stock
    return Handoff(" ".join(intent.terms) or None, variant if has_filter else None)
