# Phase 5 draft: k3s, GitOps, Ansible, OpenTofu (issue #112)

**UNVALIDATED DRAFT. Nothing here has been linted with its real tool, applied, or run.** Helm, kubectl, k3s, OpenTofu and Ansible were not available when this was written; the only automated check is `tests/test_phase5_draft.py` (valid YAML, no inline secrets, no `latest` tags). It is not wired to CI, no workflow applies it, and it needs a VPS and owner approval before anything is used.

Decisions and reasons:

- Plain Kubernetes manifests, not a Helm chart: they parse without a templating engine, so they can at least be syntax-checked offline. Convert to Helm only once `helm lint` is available.
- Image names use the placeholder `ghcr.io/OWNER/...:REPLACE_WITH_SHA`. Publishing images to GHCR is an activation that is not approved (see `docs/roadmap/completion-ledger.md`).
- No secret values anywhere. Secrets are referenced by name (`secretKeyRef`); real values come from SOPS-encrypted files the owner creates (`.sops.yaml` states the intended rule only).
- Single node, no HA: matches one VPS. Stateful Postgres in the cluster is deliberately not included; use the existing compose Postgres or a managed one until backups (#105) are activated.

Contents:

| Path | Purpose |
|---|---|
| `k8s/namespace.yaml`, `backend.yaml`, `frontend.yaml`, `worker.yaml`, `ingress.yaml` | Workloads, services, probes (`/health/`, `/ready/`), resource limits, ingress |
| `argocd/application.yaml` | Argo CD Application tracking this directory on `staging` (auto-sync off: promotion stays a PR) |
| `ansible/harden.yml` | Baseline host hardening for the VPS (SSH, firewall, unattended upgrades) |
| `opentofu/main.tf` | Cloudflare DNS record and an R2 bucket for backups (no credentials in code) |
| `.sops.yaml` | Intended SOPS rule for encrypted secret files |

Not covered, still blocked: SLO dashboards and alert delivery, nightly eval and drift pipelines (scheduling is an activation), quarterly restore drill on a real off-server copy.
