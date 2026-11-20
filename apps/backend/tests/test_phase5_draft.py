"""Only automated check for infra/phase5 (an unvalidated draft): it parses, has no inline secret values, and pins no `latest`."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3] / "infra" / "phase5"
FILES = [p for p in ROOT.rglob("*") if p.suffix in {".yaml", ".yml"} or p.name == ".sops.yaml"]


def test_every_yaml_parses():
    assert FILES
    for path in FILES:
        assert list(yaml.safe_load_all(path.read_text())), path


def test_no_inline_secret_values_or_latest_tags():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text()
        assert not re.search(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*[\"']?[A-Za-z0-9+/=_-]{12,}", text), path
        assert ":latest" not in text, path
        assert "BEGIN PRIVATE KEY" not in text and "age1" not in text, path


def test_workloads_have_probes_limits_and_no_privilege_escalation():
    for name in ("backend", "frontend"):
        for doc in yaml.safe_load_all((ROOT / "k8s" / f"{name}.yaml").read_text()):
            if doc["kind"] != "Deployment":
                continue
            c = doc["spec"]["template"]["spec"]["containers"][0]
            assert c["livenessProbe"] and c["readinessProbe"] and c["resources"]["limits"]["memory"]
            assert c["securityContext"]["allowPrivilegeEscalation"] is False
