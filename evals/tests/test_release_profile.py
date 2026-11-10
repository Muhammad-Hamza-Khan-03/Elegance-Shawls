"""A feature cannot be turned on (by default, in the image or in compose) without being scheduled, hence evaluated."""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROFILE = yaml.safe_load((ROOT / "evals" / "release_profile.yaml").read_text())
sys.path.insert(0, str(ROOT / "apps" / "backend"))


def bool_defaults() -> dict[str, bool]:
    from configuration.config import settings   # the module-level instance shadows the class of the same name
    return {name: field.default for name, field in type(settings).model_fields.items() if field.annotation is bool}


def feature_of(setting: str) -> str | None:
    return next((name for name, f in PROFILE["features"].items() if setting in f["settings"]), None)


def test_every_boolean_setting_is_classified():
    other = set(PROFILE["other_settings"])
    unclassified = [s for s in bool_defaults() if feature_of(s) is None and s not in other]
    assert unclassified == [], f"classify these in evals/release_profile.yaml (feature settings or other_settings): {unclassified}"


def test_profile_names_only_real_settings():
    known = set(bool_defaults())
    listed = {s for f in PROFILE["features"].values() for s in f["settings"]} | set(PROFILE["other_settings"])
    assert sorted(listed - known) == []


def test_nothing_that_is_on_by_default_belongs_to_an_unscheduled_feature():
    for setting, default in bool_defaults().items():
        feature = feature_of(setting)
        if default is True and feature is not None:
            assert PROFILE["features"][feature]["scheduled"], f"{setting} defaults on but feature {feature} is not scheduled for evaluation"


TRUTHY = {"true", "1", "yes", "on", "y", "t"}   # what pydantic accepts as True


def _value(raw: str) -> str:
    raw = raw.strip().strip("'\"")
    m = re.fullmatch(r"\$\{[A-Za-z0-9_]+:?[-=](.*)\}", raw)       # ${VAR:-default}: the default is what an unset deployment gets
    return (m.group(1) if m else raw).strip().strip("'\"").lower()


def assignments(path: Path) -> list[tuple[str, str]]:
    """Every NAME=value this deployment source sets: Dockerfile ENV (several per line, continuations), compose environment, env files."""
    if path.name.startswith("compose"):
        out = []
        for service in (yaml.safe_load(path.read_text()) or {}).get("services", {}).values():
            env = service.get("environment") or {}
            pairs = env.items() if isinstance(env, dict) else (e.split("=", 1) for e in env if "=" in e)
            out += [(str(k), _value(str(v))) for k, v in pairs]
        return out
    text = path.read_text().replace("\\\n", " ")
    if path.name == "Dockerfile":
        text = "\n".join(line.split(None, 1)[1] for line in text.splitlines() if re.match(r"\s*ENV\s", line))
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))   # commented examples are not settings
    return [(k, _value(v)) for k, v in re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=(\S*)", text, re.M)]


def deployment_sources() -> list[Path]:
    return [p for p in [ROOT / "apps/backend/Dockerfile", *ROOT.glob("compose*.yaml"), ROOT / "apps/backend/.env.example", *ROOT.glob(".env*example")] if p.is_file()]


def test_image_and_compose_do_not_enable_unscheduled_features():
    for path in deployment_sources():
        for name, value in assignments(path):
            feature = feature_of(name.lower())
            if feature is not None and value in TRUTHY:
                assert PROFILE["features"][feature]["scheduled"], f"{path.name} enables {name} but feature {feature} is not scheduled for evaluation"


def test_feature_looking_variables_in_deployment_files_are_classified():
    """A flag-shaped variable that is not a known setting (renamed, typo, new) cannot enable something unseen."""
    known = set(bool_defaults())
    for path in deployment_sources():
        for name, _ in assignments(path):
            if re.search(r"(_ENABLED|^ENABLE_|_ALLOW_\w+|^ALLOW_)", name) and name.lower() not in known and name != "FORWARDED_ALLOW_IPS":
                raise AssertionError(f"{path.name}: {name} looks like a feature flag but is not a backend setting; classify or rename it")


def test_scanner_sees_what_the_old_regex_missed(tmp_path):
    docker = tmp_path / "Dockerfile"
    docker.write_text("FROM x\nENV A=1 \\\n    EMBEDDING_ENABLED=Yes\nENV HF=1 WHATSAPP_VOICE_ENABLED='on'\n")
    assert ("embedding_enabled", "yes") in [(k.lower(), v) for k, v in assignments(docker)]
    assert ("whatsapp_voice_enabled", "on") in [(k.lower(), v) for k, v in assignments(docker)]
    compose = tmp_path / "compose.x.yaml"
    compose.write_text("services:\n  a:\n    environment:\n      - ASSISTANT_LLM=True\n  b:\n    environment:\n      MEMORY_EXTRACTION_ENABLED: ${X:-true}\n")
    assert [v for _, v in assignments(compose)] == ["true", "true"]
    env = tmp_path / ".env.example"
    env.write_text("# EMBEDDING_ENABLED=true\nOTEL_ENABLED=false\n")
    assert assignments(env) == [("OTEL_ENABLED", "false")]
