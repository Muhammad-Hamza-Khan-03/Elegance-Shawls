"""Detects circularity between query generators / the production vocabulary and evaluation queries (issue #139).

A query is "in-vocabulary" when every token of it already appears in the vocabulary tables that generated the data
(evals/make_roman_urdu_queries.py) or in the production parser's reviewed vocabulary (apps/backend/catalog/vocab.yaml). Scores on
in-vocabulary queries mostly measure the parser reading back its own word list, not generalisation.
"""
import importlib.util
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\W_]+", text.casefold()) if t]


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(key)
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def generator_vocabulary(root: Path = HERE) -> set[str]:
    spec = importlib.util.spec_from_file_location("make_roman_urdu_queries", root / "make_roman_urdu_queries.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    words: set[str] = set()
    for table in (module.CATEGORY, module.COLOUR, module.WARM, module.LIGHT):
        for surface in table:
            words |= set(tokens(surface))
    for frame in module.FRAMES:
        words |= set(tokens(frame.replace("{}", " ")))
    return words


def production_vocabulary(root: Path = HERE) -> set[str]:
    data = yaml.safe_load((root.parent / "apps" / "backend" / "catalog" / "vocab.yaml").read_text(encoding="utf-8"))
    return {t for s in _strings(data) for t in tokens(s)}


def overlap(queries: list[str], vocabulary: set[str]) -> dict:
    """{'n', 'fully_in_vocabulary', 'token_coverage'} over the given queries; zeros for an empty list."""
    n = len(queries)
    full = sum(1 for q in queries if (ts := tokens(q)) and all(t in vocabulary for t in ts))
    all_tokens = [t for q in queries for t in tokens(q)]
    covered = sum(1 for t in all_tokens if t in vocabulary)
    return {"n": n, "fully_in_vocabulary": full, "token_coverage": round(covered / len(all_tokens), 3) if all_tokens else 0.0}
