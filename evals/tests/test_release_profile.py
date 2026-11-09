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


def test_image_and_compose_do_not_enable_unscheduled_features():
    sources = [ROOT / "apps/backend/Dockerfile", *ROOT.glob("compose*.yaml"), ROOT / "apps/backend/.env.example"]
    pattern = re.compile(r"^\s*(?:ENV\s+)?([A-Z][A-Z0-9_]*)\s*[=:]\s*['\"]?(?:\$\{[A-Z0-9_]+:-)?(true|1)\b", re.M)
    for path in sources:
        if not path.is_file():
            continue
        for name, _ in pattern.findall(path.read_text()):
            feature = feature_of(name.lower())
            if feature is not None:
                assert PROFILE["features"][feature]["scheduled"], f"{path.name} enables {name} but feature {feature} is not scheduled for evaluation"
