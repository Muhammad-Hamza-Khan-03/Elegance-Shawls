"""Deterministic "more like this" (issue #108): same category, ranked by shared colours and material. No model, no embeddings,
so it works with the vector index off. shortcut: attribute overlap only (no style or price proximity); move to the evaluated
hybrid index once semantic search is released."""

MAX_CANDIDATES = 200


def _colours(product) -> set[str]:
    return {v.color.strip().lower() for v in product.variants if v.color and v.color.strip()}


def _material(product) -> str:
    return (product.material or "").strip().lower()


def rank_similar(base, candidates, limit: int) -> list:
    """`candidates` arrive newest first and are assumed active and of the same category; ties keep that order."""
    colours, material = _colours(base), _material(base)

    def score(product) -> int:
        return len(colours & _colours(product)) + (1 if material and material == _material(product) else 0)

    ranked = sorted((p for p in candidates if p.id != base.id), key=score, reverse=True)  # sorted() is stable
    return ranked[:limit]
