"""Container-free guards: the runtime is PostgreSQL-only and MongoDB is gone from code, dependencies, compose and CI."""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO_FILES = sorted((BACKEND / "repositories").glob("*.py"))


def tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text())


def test_the_repositories_package_has_the_expected_modules():
    assert {p.name for p in REPO_FILES} == {"__init__.py", "products.py", "staged.py", "jobs.py", "attributes.py", "enrichment.py", "embeddings.py",
                                            "admin.py", "enquiries.py", "hybrid.py", "semantic_embeddings.py", "action_executions.py", "memory.py", "customer_auth.py"}


def test_repositories_do_not_depend_on_mongo():
    banned = {"motor", "pymongo", "bson", "mongomock", "mongomock_motor"}
    for path in REPO_FILES:
        for node in ast.walk(tree(path)):
            if isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & banned, path.name
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned, path.name


def test_repositories_never_commit_so_callers_own_the_transaction():
    for path in REPO_FILES:
        calls = {n.func.attr for n in ast.walk(tree(path)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert not calls & {"commit", "rollback"}, f"{path.name} must not manage the outer transaction"


def test_the_only_staged_path_that_activates_a_product_is_publish():
    activations = []
    module = tree(BACKEND / "repositories/staged.py")
    for function in [n for n in ast.walk(module) if isinstance(n, ast.AsyncFunctionDef)]:
        for node in ast.walk(function):
            if isinstance(node, ast.Constant) and node.value == "active":
                activations.append(function.name)
    assert activations == ["publish"]


def test_approve_always_builds_a_draft():
    source = (BACKEND / "repositories/staged.py").read_text()
    assert 'status="draft"' in source and "def approve" in source
    assert "status=status" not in source        # approve never accepts a caller-chosen product status


def test_creating_a_product_defaults_to_a_draft():
    import inspect

    from repositories.products import ProductInput

    assert inspect.signature(ProductInput).parameters["status"].default == "draft"


def _imports(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(tree(path)):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add((node.module or "").split(".")[0])
    return found


def test_the_runtime_uses_the_repositories():
    for relative in ("routes/product_routes.py", "routes/ingestion_routes.py", "ingestion/pipeline.py",
                     "ingestion/worker.py", "ingestion/refresh.py"):
        assert "repositories" in _imports(BACKEND / relative) | _lazy_imports(BACKEND / relative), relative


def _lazy_imports(path: Path) -> set[str]:
    return {n.module.split(".")[0] for n in ast.walk(tree(path)) if isinstance(n, ast.ImportFrom) and n.module}


def test_no_runtime_module_imports_mongodb_drivers_or_the_mongo_database_module():
    banned = {"motor", "pymongo", "bson", "mongomock", "mongomock_motor"}
    runtime = [BACKEND / "main.py", *(BACKEND / "routes").glob("*.py"), *(BACKEND / "ingestion").glob("*.py"),
               *(BACKEND / "schemas").glob("*.py"), *(BACKEND / "security").glob("*.py"), *(BACKEND / "workers").glob("*.py"),
               *(BACKEND / "events").glob("*.py"), *(BACKEND / "llm").glob("*.py"), *(BACKEND / "utils").glob("pagination.py")]
    for path in runtime:
        names = _imports(path) | _lazy_imports(path)
        assert not names & banned, f"{path.relative_to(BACKEND)} imports {names & banned}"
        assert "database.db" not in {n.module for n in ast.walk(tree(path)) if isinstance(n, ast.ImportFrom)}, path.name


def test_the_public_listing_has_no_search_parameters_and_keeps_pagination():
    import inspect

    from routes.product_routes import get_products

    assert set(inspect.signature(get_products).parameters) == {"request", "background", "limit", "cursor", "session"}


def test_mongodb_is_gone_from_code_dependencies_and_deployment_files():
    root = BACKEND.parents[1]
    for removed in ("database/db.py", "utils/bson.py", "models/product_model.py", "scripts/import_legacy_catalog.py"):
        assert not (BACKEND / removed).exists(), removed
    for removed in ("deploy/mongo", "deploy/backup"):
        assert not (root / removed).exists(), removed
    files = [BACKEND / "requirements.txt", BACKEND / "requirements-dev.txt", BACKEND / ".env.example",
             root / "compose.yaml", root / "compose.local.yaml", root / "compose.ai.yaml", root / ".env.example",
             root / ".env.local.example", root / ".github/workflows/ci.yml", *(root / "deploy").rglob("*.sh")]
    banned = ("mongo", "motor", "bson", "atlas")
    for path in files:
        text = path.read_text().lower()
        assert not [word for word in banned if word in text], path.relative_to(root)


def test_no_python_source_mentions_mongo():
    skip = {"test_repositories_static.py", "test_refresh.py"}  # this guard names the words it forbids
    for path in BACKEND.rglob("*.py"):
        if ".venv" in path.parts or path.name in skip:
            continue
        assert "mongo" not in path.read_text().lower(), path.relative_to(BACKEND)


def test_a_stale_env_file_with_retired_mongo_keys_does_not_break_settings(monkeypatch, tmp_path):
    from configuration.config import settings as settings_class

    env = tmp_path / ".env"
    env.write_text("MONGODB_URI=ignored\nMONGO_DB_NAME=ignored\nADMIN_API_KEY=k\n")
    loaded = type(settings_class)(_env_file=env)
    assert loaded.admin_api_key == "k" and not hasattr(loaded, "MONGODB_URI")
