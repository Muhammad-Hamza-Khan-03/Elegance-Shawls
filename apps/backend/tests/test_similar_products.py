import uuid
from types import SimpleNamespace as NS

from catalog.similar import rank_similar


def product(colours, material=None):
    return NS(id=uuid.uuid4(), material=material, variants=[NS(color=c) for c in colours])


def test_more_shared_colours_rank_first_and_self_is_excluded():
    base = product(["Brown", "Black"], "Wool")
    two, one, none = product(["brown", "BLACK"]), product(["Brown"]), product(["Green"])
    assert rank_similar(base, [none, one, two, base], 10) == [two, one, none]


def test_material_counts_and_ties_keep_the_incoming_newest_first_order():
    base = product(["Brown"], "Wool")
    newer, older, matching = product(["Red"]), product(["Blue"]), product(["Pink"], " wool ")
    assert rank_similar(base, [newer, older, matching], 10) == [matching, newer, older]


def test_limit_and_missing_attributes():
    base = product([], None)
    a, b, c = product(["x"], None), product([None, " "], ""), product(["y"])
    assert rank_similar(base, [a, b, c], 2) == [a, b]
