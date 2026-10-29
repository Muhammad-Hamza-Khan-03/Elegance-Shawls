import pytest

from ingestion.refresh import select_explicit_products
from ingestion.safe_fetch import SourcePolicy
from ingestion.worker import parse_args


POLICY = SourcePolicy("shop.example", True, extra_hosts=frozenset({"www.shop.example"}))


def test_urls_are_canonicalized_to_the_exact_source_host():
    selected = select_explicit_products(
        POLICY,
        product_urls=["https://www.shop.example/products/pearl/?utm_source=qa"],
    )
    assert list(selected.products) == ["/products/pearl"]
    assert selected.sitemaps_fetched == 0


@pytest.mark.parametrize(
    "args",
    [
        ["--once", "--product-path", "/products/a", "--product-url", "https://shop.example/products/b"],
        ["--once", "--product-path", "/products/a", "--product-path", "/products/a"],
        ["--once", "--product-url", "http://shop.example/products/a"],
        ["--once", "--product-url", "https://evil.example/products/a"],
    ],
)
def test_cli_rejects_ambiguous_or_unsafe_explicit_inputs(args):
    if "--product-path" in args and "--product-url" in args:
        with pytest.raises(SystemExit):
            parse_args(args)
    else:
        parsed = parse_args(args)
        with pytest.raises(ValueError):
            select_explicit_products(POLICY, product_paths=parsed.product_path, product_urls=parsed.product_url)


def test_cli_accepts_five_repeatable_paths():
    args = ["--dry-run"]
    for handle in "abcde":
        args.extend(["--product-path", f"/products/{handle}"])
    parsed = parse_args(args)
    assert parsed.product_path == [f"/products/{handle}" for handle in "abcde"]


def test_cli_rejects_six_repeatable_paths_before_running():
    args = ["--once"]
    for handle in "abcdef":
        args.extend(["--product-path", f"/products/{handle}"])
    with pytest.raises(SystemExit):
        parse_args(args)
