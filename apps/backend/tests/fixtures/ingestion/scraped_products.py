"""Fixtures shaped like the output of the quill-store scraper (ProductShawl fields)."""
SOURCE = "https://shop.example"

PEARL = {
    "url": f"{SOURCE}/products/pearl-cashmere-shawl",
    "title": "Pearl Cashmere Shawl",
    "description": "Hand-finished 100% pure cashmere.",
    "image_urls": [
        f"{SOURCE}/cdn/shop/files/pearl_front_1800x.jpg",
        f"{SOURCE}/cdn/shop/files/pearl_back_1800x.jpg",
    ],
    "category": "shawl",
    "color": "Pearl White",
    "material": "100% Pure Cashmere",
    "sizing": "L 230cm, W 73cm",
    "weight": "140gsm",
    "origin": "Nepal",
    "price": 189.0,
    "currency": "AUD",
}

IVORY_STOLE_NO_PRICE = {
    "url": f"{SOURCE}/products/ivory-stole",
    "title": "Ivory Stole",
    "description": "Light stole.",
    "image_urls": [f"{SOURCE}/cdn/shop/files/ivory_1800x.jpg"],
    "category": "stole",
}

INVALID_NO_TITLE = {"url": f"{SOURCE}/products/broken", "description": "x", "category": "shawl"}
INVALID_CATEGORY = {**PEARL, "category": "blanket"}
