"""P1-S2: attribute vocabulary rules, provenance validation and the backfill's safety properties (no database)."""
import importlib.util
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from catalog import attributes as attrs_module
from catalog.attributes import Attribute, derive_attributes
from models.relational_model import ATTRIBUTE_KEYS, ATTRIBUTE_SOURCES

P, V = uuid.uuid4(), uuid.uuid4()
SCRIPT = Path(attrs_module.__file__).parents[1] / "scripts" / "backfill_catalog_attributes.py"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_keys_and_sources_are_the_agreed_sets():
    assert set(ATTRIBUTE_SOURCES) == {"visual_suggestion", "supplier_declared", "staff_approved", "imported"}
    assert {"color_name", "color_family", "fabric"} <= set(ATTRIBUTE_KEYS)


@pytest.mark.parametrize("bad", [
    dict(key="price"), dict(source="llm"), dict(value=""), dict(value="x" * 201),
    dict(source="staff_approved"),                                              # approval fields missing
    dict(source="staff_approved", approved_by="a"),                             # approved_at missing
    dict(approved_by="a", approved_at=datetime.now(timezone.utc)),              # approval on a non-staff source
])
def test_invalid_attributes_are_rejected(bad):
    with pytest.raises(ValueError):
        Attribute(**{"product_id": P, "key": "fabric", "value": "silk", "source": "imported", **bad})


def test_valid_attributes_distinguish_product_and_variant_and_allow_unknown():
    assert Attribute(P, "fabric", None, "imported").variant_id is None
    assert Attribute(P, "color_name", "red", "imported", variant_id=V).variant_id == V
    assert Attribute(P, "fabric", "silk", "staff_approved", approved_by="admin", approved_at=datetime.now(timezone.utc))


def test_color_resolves_from_the_vocabulary_in_every_script():
    rows = derive_attributes(P, None, [(uuid.uuid4(), c) for c in ("Black", "سرخ", "Neela", "Deep Maroon")])
    assert [r.value for r in rows if r.key == "color_name"] == ["black", "red", "blue", "maroon"]


def test_unresolved_or_ambiguous_values_stay_explicitly_unknown():
    rows = derive_attributes(P, "Handwoven Kani", [(V, "Burgundy"), (uuid.uuid4(), "Black & White"), (uuid.uuid4(), None)])
    assert [(r.key, r.value) for r in rows] == [("fabric", None), ("color_name", None), ("color_name", None), ("color_name", None)]
    assert derive_attributes(P, "Pashmina wool blend", [])[0].value is None


def test_fabric_comes_only_from_material_and_is_imported():
    rows = derive_attributes(P, "100% Pashmina", [])
    assert [(r.key, r.value, r.source, r.variant_id) for r in rows] == [("fabric", "pashmina", "imported", None)]
    assert rows[0].model_version == attrs_module.IMPORTED_VERSION and rows[0].approved_by is None


def test_backfill_never_derives_judgement_keys():
    """Composition/authenticity/pattern/occasion/season/style are not derivable: nothing but fabric and color_name is emitted."""
    rows = derive_attributes(P, "Pure pashmina, authentic, floral, bridal winter", [(V, "Red floral")])
    assert {r.key for r in rows} == {"fabric", "color_name"}
    assert {r.source for r in rows} == {"imported"}


def test_backfill_script_is_offline_and_only_touches_attributes():
    spec = importlib.util.spec_from_file_location("backfill_catalog_attributes", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "http" not in source.replace("--", "") and not {"httpx", "requests", "llm", "redis"} & set(source.split())
    assert " update(" not in source and "delete(" not in source           # products/variants are read-only here
    with pytest.raises(ValueError):
        import asyncio
        asyncio.run(module.backfill(None, 0))
