import pytest

from configuration.config import settings
from search import image_match
from search.image_match import ImageMatchError, LocalClipEmbedder, cosine


def test_cosine():
    assert cosine([1, 0], [1, 0]) == 1.0 and cosine([1, 0], [0, 1]) == 0.0 and cosine([0, 0], [1, 0]) == 0.0


def test_the_embedder_needs_a_pinned_local_model_and_refuses_bad_input():
    with pytest.raises(ImageMatchError):
        LocalClipEmbedder("", "")
    with pytest.raises(ImageMatchError):
        LocalClipEmbedder("/models/clip", "abc").embed_image(b"")
    with pytest.raises(ImageMatchError):
        LocalClipEmbedder("/models/clip", "abc").embed_image(b"x" * (image_match.MAX_IMAGE_BYTES + 1))


def test_without_a_model_path_there_is_no_embedder(monkeypatch):
    monkeypatch.setattr(settings, "image_match_model_path", "")
    monkeypatch.setattr(image_match, "_embedder", None)
    assert image_match.get_embedder() is None
