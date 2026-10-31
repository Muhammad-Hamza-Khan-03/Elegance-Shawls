"""Writes evals/datasets/roman_urdu_queries.jsonl: labelled English / Roman Urdu / Urdu-script shopping queries.

Synthetic and NOT human-reviewed ("reviewed": false). Labels are rules over product attributes (category, colour on any
variant, material class), so ground truth is objective, but the phrasing is the author's, not real customers'. Replace or
extend with logged customer queries before treating any number as production evidence. `no_answer` queries must return nothing.
"""
import hashlib
import itertools
import json
from pathlib import Path

CATEGORY = {  # surface form -> (category, language)
    "shawl": ("shawls", "en"), "shawls": ("shawls", "en"), "shaal": ("shawls", "roman_ur"), "shal": ("shawls", "roman_ur"),
    "chaadar": ("shawls", "roman_ur"), "chadar": ("shawls", "roman_ur"), "chadder": ("shawls", "roman_ur"), "شال": ("shawls", "ur"), "چادر": ("shawls", "ur"),
    "stole": ("stoles", "en"), "stoll": ("stoles", "roman_ur"), "اسٹول": ("stoles", "ur"),
    "scarf": ("scarves", "en"), "skarf": ("scarves", "roman_ur"), "muffler": ("scarves", "roman_ur"), "اسکارف": ("scarves", "ur"),
}
COLOUR = {
    "black": ("Black", "en"), "kala": ("Black", "roman_ur"), "kaala": ("Black", "roman_ur"), "siyah": ("Black", "roman_ur"), "کالا": ("Black", "ur"),
    "red": ("Red", "en"), "laal": ("Red", "roman_ur"), "lal": ("Red", "roman_ur"), "surkh": ("Red", "roman_ur"), "سرخ": ("Red", "ur"), "لال": ("Red", "ur"),
    "brown": ("Brown", "en"), "bhoora": ("Brown", "roman_ur"), "bhura": ("Brown", "roman_ur"), "بھورا": ("Brown", "ur"),
    "green": ("Green", "en"), "hara": ("Green", "roman_ur"), "سبز": ("Green", "ur"),
    "pink": ("Pink", "en"), "gulabi": ("Pink", "roman_ur"), "گلابی": ("Pink", "ur"),
    "blue": ("Blue", "en"), "neela": ("Blue", "roman_ur"), "نیلا": ("Blue", "ur"),
    "gray": ("Gray", "en"), "grey": ("Gray", "en"), "slaty": ("Gray", "roman_ur"),
}
WARM = {"garam": "roman_ur", "sardi ke liye": "roman_ur", "sardiyon ke liye": "roman_ur", "warm": "en", "winter": "en", "گرم": "ur", "سردی": "ur"}
LIGHT = {"halka": "roman_ur", "garmi ke liye": "roman_ur", "light": "en", "summer": "en", "ہلکا": "ur"}
FRAMES = ["{}", "{} chahiye", "{} dikhao", "mujhe {} chahiye", "show me {}"]
CATS = list(CATEGORY)
OUT = Path(__file__).parent / "datasets" / "roman_urdu_queries.jsonl"


def lang(*langs: str) -> str:
    s = set(langs) - {"en"}
    return "en" if not s else s.pop() if len(s) == 1 else "mixed"


def build() -> list[dict]:
    rows = []
    def add(q, languages, **rule):
        rows.append({"q": q, "lang": lang(*languages), "rule": rule, "synthetic": True, "reviewed": False})
    for c, (cat, cl) in CATEGORY.items():
        add(c, [cl], category=cat)
        for f in FRAMES[1:3]:
            add(f.format(c), [cl if f.startswith("{}") else "roman_ur" if "mujhe" in f or "dikhao" in f else cl, cl], category=cat)
    for col, (name, ol) in COLOUR.items():
        for c in ["shawl", "shaal", "chaadar", "شال", "stole", "scarf", "skarf"]:
            cat, cl = CATEGORY[c]
            add(f"{col} {c}", [ol, cl], category=cat, colour=name)
    for (w, wl), c in itertools.product(WARM.items(), ["shawl", "chaadar", "شال", "stole"]):
        cat, cl = CATEGORY[c]
        add(f"{w} {c}", [wl, cl], category=cat, material="warm")
    for (w, wl), c in itertools.product(LIGHT.items(), ["scarf", "skarf", "stole", "اسکارف"]):
        cat, cl = CATEGORY[c]
        add(f"{w} {c}", [wl, cl], category=cat, material="light")
    for col, c, w in [("kala", "chaadar", "garam"), ("laal", "shawl", "warm"), ("hara", "scarf", "halka"), ("neela", "stole", "light"), ("bhoora", "shaal", "sardi ke liye")]:
        add(f"{w} {col} {c}", ["roman_ur"], category=CATEGORY[c][0], colour=COLOUR[col][0], material="warm" if w in ("garam", "warm", "sardi ke liye") else "light")
    for q in ["delivery kitne din mein hoti hai", "hello", "aap ka naam kya hai", "iphone ki price", "return policy kya hai", "aaj ka mausam",
              "pizza order karna hai", "mujhe job chahiye", "how do I pay", "cricket score", "ڈلیوری کتنے دن میں ہوتی ہے", "آپ کا نام کیا ہے",
              "laptop chahiye", "thank you", "shukriya", "kya haal hai", "weather in lahore", "car for sale", "wedding dress", "shoes dikhao"]:
        add(q, ["roman_ur" if any(w in q for w in ("kitne", "kya", "karna", "chahiye", "aap", "ki ", "dikhao", "shukriya")) else "ur" if any("؀" <= ch <= "ۿ" for ch in q) else "en"], no_answer=True)
    # Held-out: spellings and phrasings deliberately NOT in the parser lexicon (rule labels as above). Reported separately.
    held = [("kaali chaadar", dict(category="shawls", colour="Black")), ("kaale rang ki shaal", dict(category="shawls", colour="Black")),
            ("laal rang ka stole", dict(category="stoles", colour="Red")), ("surkh rang ki chaddar", dict(category="shawls", colour="Red")),
            ("neeli shaal", dict(category="shawls", colour="Blue")), ("nila scarf", dict(category="scarves", colour="Blue")),
            ("hari chadar", dict(category="shawls", colour="Green")), ("bhoori shaal", dict(category="shawls", colour="Brown")),
            ("gulabi rang ka skarf", dict(category="scarves", colour="Pink")), ("thand ke liye shaal", dict(category="shawls", material="warm")),
            ("sardi mein pehenne ke liye chaadar", dict(category="shawls", material="warm")), ("garmiyon ke liye halka scarf", dict(category="scarves", material="light")),
            ("halki si stole", dict(category="stoles", material="light")), ("wool ki shaal", dict(category="shawls", material="warm")),
            ("pashmina wali chadar", dict(category="shawls", material="warm")), ("silk ka scarf", dict(category="scarves", material="light")),
            ("kali shaal sardi ke liye", dict(category="shawls", colour="Black", material="warm")), ("kala stole garmi ke liye", dict(category="stoles", colour="Black", material="light")),
            ("کالی چادر", dict(category="shawls", colour="Black")), ("لال شال", dict(category="shawls", colour="Red")),
            ("نیلی چادر", dict(category="shawls", colour="Blue")), ("بھوری اسٹول", dict(category="stoles", colour="Brown")),
            ("سردی کے لیے گرم شال", dict(category="shawls", material="warm")), ("گرمی کے لیے ہلکا اسکارف", dict(category="scarves", material="light")),
            ("ek achi si shal dikhana", dict(category="shawls")), ("woolen shawl for winter", dict(category="shawls", material="warm")),
            ("something warm to wear in cold weather", dict(material="warm")), ("lightweight summer wrap", dict(material="light")),
            ("ladies chaadar", dict(category="shawls")), ("mufflar chahiye", dict(category="scarves")),
            ("black shaal", dict(category="shawls", colour="Black")), ("red skarf", dict(category="scarves", colour="Red")),
            ("pink chaadar", dict(category="shawls", colour="Pink")), ("green stoll", dict(category="stoles", colour="Green")),
            ("brown wool shaal", dict(category="shawls", colour="Brown", material="warm")), ("ثقیل گرم شال", dict(category="shawls", material="warm"))]
    for q, rule in held:
        rows.append({"q": q, "lang": "roman_ur" if q.isascii() else "ur", "rule": rule, "synthetic": True, "reviewed": False, "heldout": True})
    seen, out = set(), []
    for r in rows:
        if r["q"] not in seen:
            seen.add(r["q"]); out.append(r)
    return out


if __name__ == "__main__":
    rows = build()
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(len(rows), "queries", hashlib.sha256(OUT.read_bytes()).hexdigest()[:16])
