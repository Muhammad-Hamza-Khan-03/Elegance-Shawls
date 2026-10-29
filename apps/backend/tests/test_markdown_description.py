import pytest
from bs4 import BeautifulSoup

from ingestion.extractors import ShopifyHtmlExtractor
from ingestion.markdown import html_to_markdown
from ingestion.normalize import clean_description
from tests.test_extractors import URL, load  # noqa: F401


async def extract(name):
    return await ShopifyHtmlExtractor().extract(source_url=URL, sanitized_html="", text="", raw_html=load(name))


@pytest.mark.asyncio
async def test_description_keeps_headings_paragraphs_and_lists_instead_of_one_glued_block():
    description = (await extract("structured_description.html"))["description"]
    blocks = description.split("\n\n")
    assert blocks[0] == "## Cream Pashmina Shawl – Classic Wrap"
    assert blocks[1] == "Complete your wardrobe with this **shawl**."
    assert "- Warm cream colour.\n- Medium-weight *design*." in description
    assert "## Why You'll Love It" in blocks and "### Product Details" in blocks
    assert "WrapComplete" not in description


@pytest.mark.asyncio
async def test_explicit_spec_lines_become_readable_from_the_structured_description():
    data = await extract("structured_description.html")
    assert data["material"] == "Wool blend." and data["weight"] == "Medium weight."


@pytest.mark.asyncio
async def test_markup_links_and_scripts_never_reach_the_description():
    description = (await extract("structured_description.html"))["description"]
    for forbidden in ("evil.example", "onclick", "steal", "alert", "<", ">", "t.gif", ".x{"):
        assert forbidden not in description
    assert "Read our care guide.\nSecond line." in description


@pytest.mark.asyncio
async def test_an_unrelated_block_is_never_substituted_for_the_described_text():
    html = ('<html><head><script type="application/ld+json">{"@type":"Product","name":"Wool Scarf",'
            '"description":"A genuine scarf description of reasonable length for comparison purposes only here.",'
            '"image":["https://cdn.shopify.com/a.jpg"]}</script></head>'
            '<body><div class="rte"><h2>Shipping</h2><p>Completely different shipping and returns policy text goes here.</p></div></body></html>')
    data = await ShopifyHtmlExtractor().extract(source_url=URL, sanitized_html="", text="", raw_html=html)
    assert data["description"].startswith("A genuine scarf description")


def test_html_to_markdown_structure():
    md = html_to_markdown("<div><h2>Title</h2><p>One <b>two</b></p><ul><li>a</li><li>b</li></ul><ol><li>c</li></ol>x<br>y</div>")
    assert md == "## Title\n\nOne **two**\n\n- a\n- b\n\n- c\n\nx\ny"


def test_html_to_markdown_drops_everything_unsafe_and_limits_at_a_block():
    md = html_to_markdown("<p>keep</p><iframe src=x>bad</iframe><form>bad</form><svg>bad</svg>")
    assert md == "keep"
    long = "<p>" + "a" * 60 + "</p><p>" + "b" * 60 + "</p>"
    assert html_to_markdown(long, 100) == "a" * 60


def test_clean_description_handles_html_and_plain_text():
    assert clean_description("<h1>Hi</h1><p>x &amp; y</p>", 5000) == "## Hi\n\nx & y"
    assert clean_description("Line one\r\n\r\n\r\n\r\n- bullet\n\n## Head  \x00ok", 5000) == "Line one\n\n- bullet\n\n## Head ok"
    assert clean_description("Fish &amp; chips", 5000) == "Fish & chips"
    assert clean_description("   ", 5000) is None and clean_description(None, 5000) is None
    assert len(clean_description("word " * 3000, 5000)) <= 5000


def test_plain_descriptions_from_older_runs_are_unchanged_in_meaning():
    assert clean_description("A warm shawl.\nMaterial: 100% Merino Wool\nSize: 70 x 200 cm", 5000) == \
        "A warm shawl.\nMaterial: 100% Merino Wool\nSize: 70 x 200 cm"


def test_node_and_string_inputs_agree():
    html = "<div><p>same</p></div>"
    assert html_to_markdown(html) == html_to_markdown(BeautifulSoup(html, "html.parser")) == "same"


def test_spec_lines_are_found_inside_bullets_and_bold_labels():
    from ingestion.extractors import parse_spec_lines
    assert parse_spec_lines("- **Material:** Wool blend.\n- **Weight:** Medium weight.\n- **Best for:** weddings") == {
        "material": "Wool blend.", "weight": "Medium weight."}


# ---- duplicate product images --------------------------------------------------------------------

from ingestion.normalize import dedupe_images, image_identity

BASE = "https://scarvesaustralia.com.au/cdn/shop/files/"
REAL = [  # the 12 URLs staged from the real page: 5 pictures, each listed in several sizes
    BASE + "x-classic-1226720646.jpg", BASE + "x-classic-1226720646_1800x1800.jpg",
    BASE + "x-classic-1227475036.png", BASE + "x-classic-1227475036_1800x1800.png",
    BASE + "x-35721929752629.heic", BASE + "x-35721929752629_1800x1800.heic",
    BASE + "x-35721929785397.heic",
    BASE + "x-35721929850933.heic?v=1742615705&width=1200", BASE + "x-35721929785397.heic?v=1773731095&width=1200",
    BASE + "x-classic-1227475036.png?v=1773736535&width=1200", BASE + "x-35721929752629.heic?v=1773731095&width=1200",
    BASE + "x-classic-1226720646.jpg?v=1773731095&width=1200",
]


def test_every_size_of_one_picture_is_one_image():
    kept = dedupe_images(REAL)
    assert len(kept) == 5
    assert kept == [BASE + "x-classic-1226720646.jpg", BASE + "x-classic-1227475036.png", BASE + "x-35721929752629.heic",
                    BASE + "x-35721929785397.heic", BASE + "x-35721929850933.heic?v=1742615705&width=1200"]


def test_the_plain_original_is_preferred_over_a_resized_copy_listed_first():
    assert dedupe_images([BASE + "a_1800x1800.jpg", BASE + "a.jpg?width=1200", BASE + "a.jpg"]) == [BASE + "a.jpg"]
    assert dedupe_images([BASE + "a_1800x1800.jpg"]) == [BASE + "a_1800x1800.jpg"]  # a lone copy is kept as is


def test_different_pictures_are_never_merged():
    urls = [BASE + "front.jpg", BASE + "back.jpg", BASE + "front_1x1.png", BASE + "side-2000x.jpg"]
    assert [image_identity(u) for u in urls] == ["front.jpg", "back.jpg", "front.png", "side-2000x.jpg"]
    assert len(dedupe_images(urls)) == 4


def test_a_filename_that_merely_looks_like_a_size_is_not_stripped():
    assert image_identity(BASE + "scarf_large_cream.jpg") == "scarf_large_cream.jpg"
    assert image_identity(BASE + "photo-1800x1800.jpg") == "photo-1800x1800.jpg"


@pytest.mark.asyncio
async def test_normalized_products_carry_deduplicated_images_in_order():
    from datetime import datetime, timezone
    from ingestion.normalize import normalize
    from ingestion.quill_scraper import ProductShawl
    from ingestion.safe_fetch import SourcePolicy
    policy = SourcePolicy("scarvesaustralia.com.au", True, image_hosts=frozenset({"cdn.shopify.com"}))
    scraped = ProductShawl.model_validate({"url": "https://scarvesaustralia.com.au/products/x", "title": "Cream Shawl",
                                           "description": "d", "category": "shawl", "image_urls": REAL})
    product = normalize(scraped, policy=policy, source_product_id=None, fetched_at=datetime.now(timezone.utc))["product"]
    assert len(product["images"]) == 5 and product["cover_image_url"] == product["images"][0]
