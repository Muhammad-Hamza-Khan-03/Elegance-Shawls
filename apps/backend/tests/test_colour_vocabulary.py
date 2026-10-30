import pytest

from utils import colour_vocabulary as cv


def test_version_is_pinned_so_vocabulary_changes_are_deliberate():
    assert cv.VOCABULARY_VERSION == 1
    assert len(cv.CANONICAL) == 19 and len(cv.SYNONYMS) == 12


def test_every_synonym_targets_an_approved_value_and_never_shadows_one():
    assert set(cv.SYNONYMS.values()) <= set(cv.CANONICAL)
    assert not set(cv.SYNONYMS) & set(cv.CANONICAL)


@pytest.mark.parametrize("raw,want", [("Gray", "grey"), ("  NAVY   Blue ", "navy"), ("Off-White", "ivory"),
                                      ("multicolor", "multicolour"), ("Camel", "camel")])
def test_normalizes_case_whitespace_and_synonyms(raw, want):
    assert cv.normalize(raw) == want


@pytest.mark.parametrize("raw", [None, "", "   ", "turquoise", "reddish", "dark red", "Floral"])
def test_unknown_or_blank_is_none_never_guessed(raw):
    assert cv.normalize(raw) is None
    assert cv.resolve(raw).canonical is None and cv.resolve(raw).source is None


def test_spellings_round_trip_for_every_canonical_value():
    for c in cv.CANONICAL:
        assert all(cv.normalize(s) == c for s in cv.spellings(c))
    with pytest.raises(ValueError):
        cv.spellings("turquoise")


def test_provenance_precedence_colour_beats_name_and_unknown_colour_is_not_overridden():
    assert cv.resolve("Gray", "Red") == cv.ResolvedColour("grey", "variant_color", cv.VOCABULARY_VERSION)
    assert cv.resolve("Turquoise", "Red").canonical is None      # explicit but unknown colour: name must not override
    assert cv.resolve(None, "Camel") == cv.ResolvedColour("camel", "variant_name", cv.VOCABULARY_VERSION)
    assert cv.resolve("  ", "Camel").source == "variant_name"
    assert cv.resolve(None, "Winter Edition").canonical is None
