"""Deterministic query normalisation and constraint parsing (no model, no network).

`parse_query` turns "bhoora shawal 4000 se kam" into hard constraints using only the reviewed
vocabulary in vocab.yaml. Anything it does not understand stays free text (matched lexically) and
anything it cannot represent safely (for example a negated price) is reported in `unsupported`
instead of being guessed. Constraints are never relaxed here or downstream.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

VOCAB_PATH = Path(__file__).with_name("vocab.yaml")
MAX_PRICE = 10_000_000
_URDU_MARKS = re.compile("[ً-ٰٟـ‌‍]")  # diacritics, tatweel, joiners
_URDU_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ہ", "ة": "ہ"})
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_TOKEN = re.compile(r"\w+")
_NUMBER = re.compile(r"(\d+)(k?)$")


def normalize(text: str) -> str:
    """NFKC, case-folded, Urdu marks removed, Arabic-Indic digits to ASCII."""
    text = unicodedata.normalize("NFKC", text).casefold().translate(_URDU_LETTERS)
    text = _URDU_MARKS.sub("", text)
    text = "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)
    return _THOUSANDS.sub("", text)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(normalize(text))


@dataclass(frozen=True)
class ParsedQuery:
    categories: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()           # a variant matches when its colour is any of these
    exclude_colors: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    min_price: int | None = None
    max_price: int | None = None
    in_stock: bool = False
    text: tuple[str, ...] = ()             # tokens the vocabulary does not know: matched lexically, all required
    unsupported: tuple[str, ...] = ()      # understood but not safely representable: the search returns nothing

    def filters(self) -> dict:
        """The constraint dict used by the evaluation datasets (empty values omitted)."""
        out: dict = {}
        if len(self.categories) == 1:
            out["category"] = self.categories[0]
        elif self.categories:
            out["categories"] = list(self.categories)
        for key in ("colors", "exclude_colors", "materials"):
            if getattr(self, key):
                out[key] = list(getattr(self, key))
        for key in ("min_price", "max_price"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        if self.in_stock:
            out["in_stock"] = True
        return out


@dataclass(frozen=True)
class Vocabulary:
    terms: dict[tuple[str, ...], tuple[str, str]]      # token phrase -> (kind, canonical value)
    longest: int

    def canonical(self, kind: str, text: str | None) -> frozenset[str]:
        """Canonical values of a kind found in free catalogue text (empty when unknown)."""
        tokens = tokenize(text or "")
        found, i = set(), 0
        while i < len(tokens):
            for size in range(min(self.longest, len(tokens) - i), 0, -1):
                hit = self.terms.get(tuple(tokens[i:i + size]))
                if hit and hit[0] == kind:
                    found.add(hit[1])
                    i += size - 1
                    break
            i += 1
        return frozenset(found)


def _build(raw: dict) -> Vocabulary:
    terms: dict[tuple[str, ...], tuple[str, str]] = {}

    def add(kind: str, value: str, phrase: str) -> None:
        key = tuple(tokenize(str(phrase)))
        if not key:
            raise ValueError(f"empty vocabulary term {phrase!r}")
        if key in terms and terms[key] != (kind, value):
            raise ValueError(f"vocabulary term {phrase!r} is ambiguous: {terms[key]} vs {(kind, value)}")
        terms[key] = (kind, value)

    for kind, section in (("category", "categories"), ("color", "colors"), ("material", "materials")):
        for value, phrases in raw[section].items():
            for phrase in [value, *phrases]:
                add(kind, value, phrase)
    for phrase in raw["availability"]["in_stock"]:
        add("in_stock", "in_stock", phrase)
    for name in ("max_before", "min_before", "max_after", "min_after", "between_start", "between_joiner", "currency_words"):
        for phrase in raw["price"][name]:
            add(name, name, phrase)
    for name in ("before", "after"):
        for phrase in raw["negation"][name]:
            add("neg_" + name, name, phrase)
    for phrase in raw["stopwords"]:
        add("stop", "stop", phrase)
    return Vocabulary(terms, max(len(k) for k in terms))


@lru_cache(maxsize=1)
def load_vocabulary() -> Vocabulary:
    return _build(yaml.safe_load(VOCAB_PATH.read_text(encoding="utf-8")))


def _segment(tokens: list[str], vocab: Vocabulary) -> list[tuple[str, str]]:
    """Greedy longest-phrase segmentation into (kind, value); numbers are ("num", digits), the rest ("word", token)."""
    items, i = [], 0
    while i < len(tokens):
        for size in range(min(vocab.longest, len(tokens) - i), 0, -1):
            hit = vocab.terms.get(tuple(tokens[i:i + size]))
            if hit:
                items.append(hit)
                i += size
                break
        else:
            items.append(("num" if _NUMBER.match(tokens[i]) else "word", tokens[i]))
            i += 1
    return items


def _amount(value: str) -> int | None:
    digits, thousand = _NUMBER.match(value).groups()
    amount = int(digits) * (1000 if thousand else 1)
    return amount if amount <= MAX_PRICE else None


def parse_query(query: str | None, vocab: Vocabulary | None = None) -> ParsedQuery:
    vocab = vocab or load_vocabulary()
    items = [it for it in _segment(tokenize(query or ""), vocab) if it[0] not in ("stop", "currency_words")]
    found: dict[str, set[str]] = {"category": set(), "color": set(), "exclude": set(), "material": set()}
    mins, maxs, text, unsupported = [], [], [], []
    in_stock = False

    def kind(idx: int) -> str | None:
        return items[idx][0] if 0 <= idx < len(items) else None

    used = set()  # indexes of operators and range parts already attached to a number
    for i, (k, value) in enumerate(items):
        if i in used:
            continue
        if k == "num":
            amount = _amount(value)
            if kind(i - 1) == "between_start" and kind(i + 1) == "between_joiner" and kind(i + 2) == "num":
                high = _amount(items[i + 2][1])
                used.update({i - 1, i + 1, i + 2})
                if amount is None or high is None:
                    unsupported.append("price out of range")
                else:
                    mins.append(min(amount, high))
                    maxs.append(max(amount, high))
                continue
            op = i - 1 if kind(i - 1) in ("max_before", "min_before") else i + 1 if kind(i + 1) in ("max_after", "min_after") else None
            if op is None or op in used:
                text.append(value)  # a bare number has no stated meaning: never guessed as a price
                continue
            used.add(op)
            if amount is None:
                unsupported.append("price out of range")
            else:
                (maxs if items[op][0].startswith("max") else mins).append(amount)
        elif k == "color" and (kind(i - 1) == "neg_before" or kind(i + 1) == "neg_after"):
            found["exclude"].add(value)
        elif k in found:
            found[k].add(value)
        elif k == "in_stock":
            in_stock = True
        elif k == "word":
            text.append(value)
    for i, (k, _) in enumerate(items):
        # Only colours can be excluded; any other negation or dangling operator is reported, never dropped.
        if k == "neg_before" and kind(i + 1) != "color" or k == "neg_after" and kind(i - 1) != "color":
            unsupported.append("negation is only supported for colours")
        elif k in ("max_before", "min_before", "max_after", "min_after") and i not in used:
            unsupported.append("price operator without a number")
        elif k == "between_start" and i not in used:
            unsupported.append("incomplete price range")
    return ParsedQuery(
        categories=tuple(sorted(found["category"])), colors=tuple(sorted(found["color"])),
        exclude_colors=tuple(sorted(found["exclude"])), materials=tuple(sorted(found["material"])),
        min_price=max(mins) if mins else None, max_price=min(maxs) if maxs else None,
        in_stock=in_stock, text=tuple(text), unsupported=tuple(dict.fromkeys(unsupported)),
    )
