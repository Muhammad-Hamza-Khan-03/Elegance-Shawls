"""One-shot monthly refresh: discovery, selection, staging guard, CLI hygiene (no database needed).

Everything runs against mocked HTTP (httpx.MockTransport); the database-backed behaviour is covered in
tests/integration/test_refresh_db.py against a real PostgreSQL.
"""
import json
from pathlib import Path

import httpx
import pytest

from configuration.config import settings
from ingestion import refresh
from ingestion.refresh import (
    ProductSelectionError, StagingGuardError, assert_staging, enabled_sources, redact,
    render_summary, run_cli, run_refresh, select_explicit_products,
)
from ingestion.safe_fetch import DomainRateLimiter, SafeFetcher, SourcePolicy
from ingestion.sitemap import DiscoveryError, canonical_product_path, discover_products, parse_sitemap
from tests.refresh_support import (  # noqa: F401  (site is a fixture)
    NEW, OLD, POLICY, ROOT, SCHEME, SOURCES, SRV, index, product_page, site, src, urlset,
)

# ---- discovery -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sitemap_index_is_traversed_and_non_product_sitemaps_ignored(site):
    site.xml(ROOT, index("https://shop.example/sitemap_products_1.xml?from=1&amp;to=2",
                         "https://www.shop.example/sitemap_products_2.xml", "https://shop.example/sitemap_pages_1.xml"))
    site.xml("/sitemap_products_1.xml?from=1&to=2", urlset(("https://shop.example/products/a", OLD)))
    site.xml("/sitemap_products_2.xml", urlset(("https://shop.example/products/b", OLD)))
    found = await discover_products(site.factory(), POLICY)
    assert sorted(found.products) == ["/products/a", "/products/b"] and found.sitemaps_fetched == 3
    assert not any("pages" in p for _, p in site.log) and found.ignored == 1




@pytest.mark.asyncio
async def test_nested_index_depth_is_bounded(site):
    site.xml(ROOT, index("https://shop.example/sitemap_products_1.xml"))
    site.xml("/sitemap_products_1.xml", index("https://shop.example/sitemap_products_2.xml"))
    site.xml("/sitemap_products_2.xml", index("https://shop.example/sitemap_products_3.xml"))
    with pytest.raises(DiscoveryError) as err:
        await discover_products(site.factory(), POLICY)
    assert err.value.code == "sitemap_invalid"




@pytest.mark.asyncio
async def test_sitemap_index_child_on_unapproved_host_is_a_policy_violation(site):
    site.xml(ROOT, index("https://evil.example/sitemap_products_1.xml"))
    with pytest.raises(DiscoveryError) as err:
        await discover_products(site.factory(), POLICY)
    assert err.value.code == "source_policy_violation" and ("evil.example", "/sitemap_products_1.xml") not in site.log




def test_canonicalization_collapses_www_query_fragment_and_slash():
    for loc in ("https://www.shop.example/products/a", "https://SHOP.example/products/a/", "https://shop.example/products/a?utm=1",
                "https://www.shop.example/products/a/?x=1#frag"):
        assert canonical_product_path(loc, POLICY) == "/products/a"


@pytest.mark.parametrize("loc", [
    "https://shop.example/", "https://shop.example/collections/all", "https://shop.example/pages/about",
    "https://shop.example/blogs/news/post", "https://shop.example/products/", "https://shop.example/products/a/b",
    "https://shop.example/products/a b",
])
def test_non_product_urls_are_ignored(loc):
    assert canonical_product_path(loc, POLICY) is None


def test_explicit_selection_accepts_exactly_five_product_paths_without_sitemap_discovery():
    selected = select_explicit_products(
        POLICY, product_paths=[f"/products/{handle}" for handle in "abcde"]
    )
    assert list(selected.products) == [f"/products/{handle}" for handle in "abcde"]
    assert selected.sitemaps_fetched == 0


@pytest.mark.parametrize("values", [
    [f"/products/{handle}" for handle in "abcdef"],
    ["https://evil.example/products/a"],
    ["https://shop.example/collections/all"],
    ["/products/a", "/products/a"],
])
def test_explicit_selection_rejects_over_limit_unsafe_non_product_and_duplicates(values):
    kwargs = {"product_urls": values} if values and values[0].startswith("http") else {"product_paths": values}
    with pytest.raises(ProductSelectionError):
        select_explicit_products(POLICY, **kwargs)


def test_explicit_selection_rejects_ambiguous_path_and_url_inputs():
    with pytest.raises(ProductSelectionError):
        select_explicit_products(POLICY, product_paths=["/products/a"], product_urls=["https://shop.example/products/b"])










@pytest.mark.asyncio
async def test_exactly_the_cap_is_allowed(site, monkeypatch):
    monkeypatch.setattr(settings, "ingestion_max_urls_per_source", 2)
    assert len((await discover_products(site.factory(), POLICY)).products) == 2




@pytest.mark.asyncio
async def test_transient_sitemap_failures_are_retried(site):
    calls = {"n": 0}
    original = site.handler

    def flaky(request):
        calls["n"] += 1
        return httpx.Response(503, text="busy") if calls["n"] == 1 else original(request)

    async def dns(_):
        return ["93.184.216.34"]
    fetcher = SafeFetcher(POLICY, resolver=dns, rate_limiter=DomainRateLimiter(0),
                          client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(flaky)))
    async def nosleep(_): return None
    assert len((await discover_products(fetcher, POLICY, sleep=nosleep)).products) == 2 and calls["n"] == 2


def test_unauthorized_or_unconfigured_sources_never_run(monkeypatch):
    for domain, authorized in (("shop.example", False), ("", True)):
        monkeypatch.setattr(settings, "ingestion_source_domain", domain)
        monkeypatch.setattr(settings, "ingestion_source_authorized", authorized)
        assert enabled_sources() == []
    monkeypatch.setattr(settings, "ingestion_source_domain", "shop.example")
    monkeypatch.setattr(settings, "ingestion_source_authorized", True)
    assert [s[0] for s in enabled_sources()] == [settings.ingestion_source_id]






# ---- failures ------------------------------------------------------------------------------













# ---- runtime and request limits ------------------------------------------------------------









# ---- never publish / archive / delete -------------------------------------------------------





def test_refresh_code_has_no_publish_archive_or_delete_paths():
    code = (Path(refresh.__file__).read_text() + (Path(refresh.__file__).parent / "sitemap.py").read_text())
    for forbidden in ("delete_one", "delete_many", "drop(", "is_active", "StagedStatus.PUBLISHED", "StagedStatus.ARCHIVED",
                      "repositories.products", "repositories import products", "staged_repo", "set_status", ".delete("):
        assert forbidden not in code


# ---- dry-run and discovery-only -------------------------------------------------------------





@pytest.mark.asyncio
async def test_discovery_only_needs_no_database(site):
    summary = await run_refresh(None, sources=SOURCES, mode="discovery-only", fetcher_factory=lambda p: site.factory(p))
    assert summary["termination_reason"] == "completed" and src(summary)["discovered_urls"] == 2
    assert site.products_fetched() == []


# ---- staging guard, CLI, secrets --------------------------------------------------------------

@pytest.mark.parametrize("name", ["elegance_shawls_staging", "staging", "es-staging", "staging_2026", "ES_STAGING"])
def test_staging_names_pass_the_guard(name):
    assert_staging(name)


@pytest.mark.parametrize("name", ["elegance_shawls", "production", "elegance_shawls_prod", "prod_staging", "stagingx", "xstaging",
                                  "test", "", "restaging"])
def test_non_staging_names_are_refused(name):
    with pytest.raises(StagingGuardError):
        assert_staging(name)


@pytest.mark.asyncio
async def test_cli_refuses_a_non_staging_database_before_connecting(monkeypatch, capsys):
    monkeypatch.setattr(settings, "database_url", SCHEME + "u:p@h/elegance_shawls")
    async def forbidden(mode): raise AssertionError("must not connect")
    monkeypatch.setattr(refresh, "open_db", forbidden)
    for mode in ("once", "dry-run", "discovery-only"):
        assert await run_cli(mode) == 1
    assert capsys.readouterr().out.count("staging_guard_failed") == 3








def test_secrets_are_redacted_from_summaries_and_logs(monkeypatch):
    uri = SCHEME + "user:hunter2@cluster.example.net/db"
    monkeypatch.setattr(settings, "database_url", uri)
    monkeypatch.setattr(settings, "admin_api_key", "super-secret-admin-key")
    text = render_summary({"error_samples": [f"failed {uri}", "key super-secret-admin-key", "Bearer abc.def.ghi",
                                            SCHEME + "other:pw@host/x", SRV + "legacy:pw@old/x", "X-Admin-Key: leak"]})
    for secret in ("hunter2", "super-secret-admin-key", "abc.def.ghi", "other:pw", "legacy:pw", "leak", "cluster.example"):
        assert secret not in text
    import logging
    record = logging.LogRecord("x", logging.ERROR, "f", 1, "boom %s", (uri,), None)
    assert "hunter2" not in refresh.RedactingFormatter("%(message)s").format(record)


@pytest.mark.asyncio
async def test_unexpected_errors_print_only_the_error_type(monkeypatch, capsys):
    uri = SCHEME + "user:hunter2@host/elegance_shawls_staging"
    monkeypatch.setattr(settings, "database_url", uri)
    async def failing(mode): raise RuntimeError(f"cannot connect to {uri}")
    monkeypatch.setattr(refresh, "open_db", failing)
    assert await run_cli("once") == 1
    out = capsys.readouterr().out
    assert "hunter2" not in out and "internal_error" in out and "RuntimeError" in out




def test_worker_flags_and_default_mode_are_preserved():
    from ingestion.worker import parse_args
    assert not any(vars(parse_args([]))[k] for k in ("once", "dry_run", "discovery_only"))
    a = parse_args(["--once", "--summary-file", "x.json"])
    assert a.once and a.summary_file == "x.json"
    assert parse_args(["--dry-run"]).dry_run and parse_args(["--discovery-only"]).discovery_only
    import argparse
    with pytest.raises(SystemExit):
        parse_args(["--database-url", SCHEME + "x"])  # secrets are never command-line arguments


# ---- local monthly helper and CI hygiene ------------------------------------------------------

import fcntl
import os
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "apps/backend/scripts/monthly_refresh.sh"
needs_flock = pytest.mark.skipif(shutil.which("flock") is None, reason="flock not installed")


def run_script(tmp_path, *args, env=None, stub_exit=0):
    stub = tmp_path / "fake_python"
    stub.write_text(f"#!/usr/bin/env bash\necho \"$@\" > '{tmp_path}/argv'\necho '{{\"termination_reason\": \"stub\"}}'\nexit {stub_exit}\n")
    stub.chmod(0o755)
    environ = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "PYTHON": str(stub), "DATABASE_URL": SCHEME + "u:p@h/elegance_shawls_staging",
               "REFRESH_LOCK_FILE": str(tmp_path / "lock"), "REFRESH_OUTPUT_DIR": str(tmp_path / "out"), **(env or {})}
    return subprocess.run(["bash", str(SCRIPT), *args], env=environ, capture_output=True, text=True, timeout=30)


@needs_flock
def test_helper_runs_the_bounded_one_shot_and_writes_an_ignored_summary(tmp_path):
    result = run_script(tmp_path)
    assert result.returncode == 0
    assert (tmp_path / "argv").read_text().split()[:3] == ["-m", "ingestion.worker", "--once"]
    assert "--summary-file" in (tmp_path / "argv").read_text()
    assert (tmp_path / "out/.gitignore").read_text() == "*\n"


@needs_flock
@pytest.mark.parametrize("mode", ["--once", "--dry-run", "--discovery-only"])
def test_helper_passes_through_only_the_supported_modes(tmp_path, mode):
    assert run_script(tmp_path, mode).returncode == 0
    assert mode in (tmp_path / "argv").read_text()


@needs_flock
@pytest.mark.parametrize("args", [("--database-url", SCHEME + "u:p@h/db"), (SCHEME + "u:p@h/db",), ("--once", "--dry-run"), ("--admin-key=x",)])
def test_helper_never_accepts_secrets_or_other_arguments(tmp_path, args):
    result = run_script(tmp_path, *args)
    assert result.returncode == 64 and not (tmp_path / "argv").exists()
    assert "u:p" not in result.stdout + result.stderr


@needs_flock
@pytest.mark.parametrize("name", ["elegance_shawls", "elegance_shawls_prod", "production", "prod_staging", "stagingx"])
def test_helper_refuses_a_database_that_is_not_clearly_staging(tmp_path, name):
    result = run_script(tmp_path, env={"DATABASE_URL": SCHEME + "u:p@h/" + name})
    assert result.returncode == 2 and not (tmp_path / "argv").exists()


@needs_flock
def test_helper_reads_the_database_name_from_the_ignored_env_file_without_printing_secrets(tmp_path):
    backend = tmp_path / "backend"
    (backend / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, backend / "scripts/monthly_refresh.sh")
    (backend / ".env").write_text(f"DATABASE_URL={SCHEME}user:hunter2@host/elegance_shawls_prod\n")
    environ = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "REFRESH_LOCK_FILE": str(tmp_path / "lock")}
    result = subprocess.run(["bash", str(backend / "scripts/monthly_refresh.sh")], env=environ, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2 and "hunter2" not in result.stdout + result.stderr


@needs_flock
def test_helper_refuses_when_no_database_name_is_configured_anywhere(tmp_path):
    backend = tmp_path / "backend"  # a clean copy, so a developer's real .env cannot supply a name
    (backend / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, backend / "scripts/monthly_refresh.sh")
    environ = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "REFRESH_LOCK_FILE": str(tmp_path / "lock")}
    result = subprocess.run(["bash", str(backend / "scripts/monthly_refresh.sh")], env=environ, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2


@needs_flock
def test_helper_blocks_overlapping_runs(tmp_path):
    with open(tmp_path / "lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_script(tmp_path)
    assert result.returncode == 75 and not (tmp_path / "argv").exists()
    assert run_script(tmp_path).returncode == 0  # released lock: runs again


@needs_flock
def test_helper_returns_the_failure_exit_code(tmp_path):
    assert run_script(tmp_path, stub_exit=1).returncode == 1


def test_no_github_workflow_runs_the_refresh_or_touches_a_staging_database():
    for workflow in (REPO / ".github/workflows").glob("*.y*ml"):
        text = workflow.read_text()
        assert "ingestion.worker" not in text and "monthly" not in workflow.name
        assert "STAGING_DATABASE_URL" not in text and "elegance_shawls_staging" not in text
        assert "cron:" not in text  # nothing here may schedule a refresh


def test_helper_script_has_no_credentials_or_production_targets():
    text = SCRIPT.read_text()
    assert SCHEME not in text and SRV not in text and "set -x" not in text
    assert "onrender.com" not in text and "vercel" not in text.lower()


# ---- --discovery-only needs no database credentials or database modules -----------------------------

import sys

BACKEND = Path(__file__).resolve().parents[1]
FORBIDDEN_MODULES = ("database", "database.db", "database.pg", "sqlalchemy", "asyncpg", "motor", "motor.motor_asyncio",
                     "pymongo", "repositories", "ingestion.pipeline", "ingestion.safe_fetch", "httpx")
# Explicitly unauthorized, so even a developer's local .env cannot make these subprocess runs touch a real source.
HERMETIC = {"INGESTION_SOURCE_AUTHORIZED": "false", "INGESTION_SOURCE_DOMAIN": "", "INGESTION_SOURCE_ID": "t"}


def run_entry(*flags, env=None, snippet=None):
    environ = {"PATH": os.environ["PATH"], "HOME": "/nonexistent", **HERMETIC, **(env or {})}
    if snippet:
        cmd = [sys.executable, "-c", snippet]
    else:
        cmd = [sys.executable, "-m", "ingestion.worker", *flags]
    return subprocess.run(cmd, cwd=BACKEND, env=environ, capture_output=True, text=True, timeout=60)


def test_discovery_only_starts_without_database_credentials():
    result = run_entry("--discovery-only", env={"DATABASE_URL": SCHEME + "u:p@h/elegance_shawls_staging"})
    out = json.loads(result.stdout)
    assert out["termination_reason"] == "no_authorized_sources"  # reached dispatch; no source is configured here
    assert "Field required" not in result.stdout + result.stderr and "Traceback" not in result.stderr
    assert result.returncode == 1


def test_discovery_only_never_loads_database_or_fetch_modules_before_a_source_is_authorized():
    snippet = (
        "import runpy, sys, json\n"
        "sys.argv = ['ingestion.worker', '--discovery-only']\n"
        "try:\n    runpy.run_module('ingestion.worker', run_name='__main__')\n"
        "except SystemExit:\n    pass\n"
        f"print('LOADED=' + json.dumps([m for m in {FORBIDDEN_MODULES!r} if m in sys.modules]))\n"
    )
    result = run_entry(snippet=snippet, env={"DATABASE_URL": SCHEME + "u:p@h/elegance_shawls_staging"})
    loaded = [line for line in result.stdout.splitlines() if line.startswith("LOADED=")]
    forbidden = set(json.loads(loaded[0][7:])) - {"ingestion.safe_fetch", "httpx"}  # fetching is allowed; databases are not
    assert forbidden == set(), forbidden


@pytest.mark.parametrize("name", ["elegance_shawls_prod", "elegance_shawls", "production", "prod_staging", "stagingx", ""])
def test_bad_database_names_are_refused_before_settings_or_source_access(name):
    env = {"DATABASE_URL": SCHEME + "u:p@h/" + name if name else ""}  # set explicitly (even empty) so a local .env cannot fill it in
    snippet = (
        "import runpy, sys, json\n"
        "sys.argv = ['ingestion.worker', '--discovery-only']\n"
        "try:\n    runpy.run_module('ingestion.worker', run_name='__main__')\n"
        "except SystemExit as e:\n    print('EXIT=%s' % e.code)\n"
        "print('LOADED=' + json.dumps([m for m in ('configuration.config','ingestion.safe_fetch','ingestion.sitemap','httpx','database','sqlalchemy','motor') if m in sys.modules]))\n"
    )
    result = run_entry(snippet=snippet, env=env)
    assert "EXIT=1" in result.stdout and "staging_guard_failed" in result.stdout
    assert "LOADED=[]" in result.stdout  # nothing that could reach a source or database was even imported
    assert "Traceback" not in result.stderr and "Field required" not in result.stdout + result.stderr


def test_a_connection_string_in_the_environment_is_never_printed():
    secret = SCHEME + "user:hunter2@host.example/elegance_shawls_staging"
    result = run_entry("--discovery-only", env={"DATABASE_URL": secret})
    assert "hunter2" not in result.stdout + result.stderr and secret not in result.stdout + result.stderr


def test_a_missing_database_name_is_refused_before_settings_load(monkeypatch):
    from ingestion import staging_guard
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)  # simulate a checkout without a .env
    with pytest.raises(StagingGuardError):
        staging_guard.prepare_discovery_environment()


@pytest.mark.asyncio
async def test_discovery_only_cli_succeeds_without_any_database_connection(monkeypatch, site, capsys):
    monkeypatch.setattr(settings, "database_url", SCHEME + "u:p@h/elegance_shawls_staging")
    monkeypatch.setattr(settings, "ingestion_source_domain", "shop.example")
    monkeypatch.setattr(settings, "ingestion_source_authorized", True)
    async def forbidden(mode): raise AssertionError("discovery-only must not connect to the database")
    monkeypatch.setattr(refresh, "open_db", forbidden)
    assert await run_cli("discovery-only", fetcher_factory=lambda p: site.factory(p)) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["totals"]["discovered_urls"] == 2 and printed["totals"]["jobs_created"] == 0
    assert site.products_fetched() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["discovery-only", "dry-run", "once"])
async def test_a_non_staging_database_is_refused_before_any_source_access(monkeypatch, mode, capsys):
    monkeypatch.setattr(settings, "database_url", SCHEME + "u:p@h/elegance_shawls_prod")
    def no_fetch(policy): raise AssertionError("source must not be contacted")
    async def no_db(mode): raise AssertionError("database must not be opened")
    monkeypatch.setattr(refresh, "open_db", no_db)
    assert await run_cli(mode, fetcher_factory=no_fetch) == 1
    assert "staging_guard_failed" in capsys.readouterr().out
