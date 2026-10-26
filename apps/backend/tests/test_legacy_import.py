import copy
import json
import sys

import mongomock
import pytest

from scripts import import_legacy_catalog as importer


def legacy_product():
    return {
        "name": "Cashmere Shawl", "slug": "cashmere-shawl",
        "category": {"name": "shawl"}, "price": {"amount": 4500, "currency": "PKR"},
        "status": "active", "sizing": "Free Size", "item_number": 12,
        "variations": [
            {"color": "Blue", "image_url": "https://images.example.com/front.jpg"},
            {"color": "blue", "image_url": "https://images.example.com/back.jpg"},
        ],
    }


def test_import_preserves_source_and_never_invents_available_inventory():
    source = legacy_product()
    original = copy.deepcopy(source)
    result = importer.prepare_product(source)
    assert source == original
    assert result.status.value == "draft"
    assert len(result.variants) == 1
    assert len(result.images) == 2
    assert result.variants[0].stock == 0
    assert result.variants[0].stock_status == "Out of stock"
    assert result.price == 4500
    source["status"] = "archived"
    assert importer.prepare_product(source).status.value == "archived"


@pytest.mark.parametrize("field,value", [("category", {"name": "unknown"}), ("price", {"amount": 2.5, "currency": "PKR"})])
def test_ambiguous_data_requires_review(field, value):
    source = legacy_product()
    source[field] = value
    with pytest.raises(ValueError):
        importer.prepare_product(source)


def test_apply_is_idempotent_and_does_not_overwrite_existing_products(tmp_path, monkeypatch, capsys):
    snapshot = tmp_path / "products.json"
    snapshot.write_text(json.dumps([legacy_product()]))
    client = mongomock.MongoClient()
    original = {"slug": "cashmere-shawl", "preserve": "owner data"}
    client.elegance_shawls.products.insert_one(original)
    monkeypatch.setattr(importer, "MongoClient", lambda *args, **kwargs: client)
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost/test-fixture-only")
    monkeypatch.setattr(sys, "argv", ["importer", "--input", str(snapshot), "--apply"])
    assert importer.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["inserted"] == 0
    assert result["skipped_existing"] == 1
    assert client.elegance_shawls.products.find_one({"slug": "cashmere-shawl"})["preserve"] == "owner data"


def test_invalid_input_prevents_all_writes(tmp_path, monkeypatch, capsys):
    invalid = legacy_product()
    invalid["slug"] = "invalid-product"
    invalid["variations"][0]["image_url"] = "file:///private/image.jpg"
    snapshot = tmp_path / "products.json"
    snapshot.write_text(json.dumps([legacy_product(), invalid]))
    monkeypatch.setattr(sys, "argv", ["importer", "--input", str(snapshot), "--apply"])
    monkeypatch.setattr(importer, "MongoClient", lambda *a, **k: pytest.fail("must not open target for invalid input"))
    assert importer.main() == 1
    assert json.loads(capsys.readouterr().out)["inserted"] == 0
