"""Image embeddings for "find similar products from a photo": a LOCAL CLIP model, offline, one pinned directory.

Same posture as embeddings/providers/local_e5.py: sentence-transformers and Pillow are optional dependencies imported lazily
(requirements-local-e5.txt plus `pip install pillow`), the model is a directory you fetched yourself and its tree digest must
match IMAGE_MATCH_MODEL_REVISION, nothing is downloaded and no customer image leaves the process. Errors are fixed strings.
"""
import io
import math
from typing import Protocol

from configuration.config import settings

MODEL = "clip-ViT-B-32"
DIMENSION = 512
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 24_000_000


class ImageMatchError(Exception):
    """Fixed-string failure: missing dependency, unpinned/mismatched model, undecodable or oversized image."""


class ImageEmbedder(Protocol):
    model: str

    def embed_image(self, data: bytes) -> list[float]: ...


def cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


class LocalClipEmbedder:
    model = MODEL

    def __init__(self, model_dir: str, revision: str):
        if not model_dir or not revision:
            raise ImageMatchError("image model path and revision are both required")
        self._dir, self._revision, self._model = model_dir, revision, None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImageMatchError("sentence-transformers and pillow are not installed") from exc
            from embeddings.providers.local_e5 import model_tree_digest
            try:
                if model_tree_digest(self._dir) != self._revision:
                    raise ImageMatchError("image model revision mismatch")
                self._model = SentenceTransformer(self._dir, device="cpu", local_files_only=True)
            except OSError as exc:
                raise ImageMatchError("image model directory is missing") from exc
        return self._model

    def embed_image(self, data: bytes) -> list[float]:
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ImageMatchError("image is empty or too large")
        try:
            from PIL import Image
            image = Image.open(io.BytesIO(data))
            if image.width * image.height > MAX_PIXELS:
                raise ImageMatchError("image has too many pixels")
            vector = self._load().encode(image.convert("RGB"), normalize_embeddings=True)
        except ImageMatchError:
            raise
        except ImportError as exc:
            raise ImageMatchError("sentence-transformers and pillow are not installed") from exc
        except Exception as exc:                       # PIL decode errors, torch errors: never echo their text
            raise ImageMatchError("image could not be embedded") from exc
        values = [float(x) for x in vector]
        if len(values) != DIMENSION:
            raise ImageMatchError("unexpected embedding size")
        return values


_embedder: ImageEmbedder | None = None


def get_embedder() -> ImageEmbedder | None:
    """The configured local embedder, or None when photo matching is not configured."""
    global _embedder
    if _embedder is None and settings.image_match_model_path:
        _embedder = LocalClipEmbedder(settings.image_match_model_path, settings.image_match_model_revision)
    return _embedder
