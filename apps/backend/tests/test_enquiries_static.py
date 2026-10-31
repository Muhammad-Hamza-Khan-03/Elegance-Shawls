"""M1-S4 guard rails that need no database: the enquiry code only records a reference; it never sends or orders."""
import ast
import re
from pathlib import Path

from repositories.enquiries import ALPHABET, new_reference

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "routes/enquiry_routes.py", ROOT / "repositories/enquiries.py"]
NETWORK = {"httpx", "requests", "aiohttp", "urllib", "smtplib", "socket", "workers", "llm"}


def test_enquiry_modules_import_nothing_that_can_send_a_message():
    for path in FILES:
        for node in ast.walk(ast.parse(path.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not {n.split(".")[0] for n in names} & NETWORK, path.name


def test_references_use_the_unambiguous_alphabet():
    assert not set("01OI") & set(ALPHABET)
    assert all(re.fullmatch(r"ES-[A-HJ-NP-Z2-9]{6}", new_reference()) for _ in range(200))
