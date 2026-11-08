#!/usr/bin/env bash
# Read-only Git hygiene audit (docs/REPO_HYGIENE.md). Changes nothing: it only prints.
#   scripts/repo_audit.sh            # worktrees + branches
# Needs `git`; open PR heads are marked when `gh` is installed and logged in.
set -euo pipefail
git fetch origin --prune -q
CANON=(origin/main origin/staging origin/staging-integration)
open_heads=""; command -v gh >/dev/null && open_heads=$(gh pr list --state open --json headRefName -q '.[].headRefName' 2>/dev/null || true)
is_open() { grep -qxF -- "$1" <<<"$open_heads"; }
held() { git for-each-ref --contains "$1" --count=1 --format=x refs/heads refs/remotes refs/tags | grep -q x; }
printf '== worktrees (%s)\n' "$(git worktree list | wc -l)"
git worktree list --porcelain | awk '/^worktree /{p=substr($0,10)} /^HEAD /{h=$2} /^branch /{b=substr($0,19)} /^detached/{b="(detached)"} /^$/{print p"\t"h"\t"b; b=""}' |
while IFS=$'\t' read -r path head br; do
  [ -d "$path" ] || { echo "MISSING   $path ($br)  -> git worktree prune"; continue; }
  dirty=$(git -C "$path" status --porcelain | wc -l)
  uniq=$(git rev-list --count "$head" --not "${CANON[@]}")
  tag=OK; [ "$uniq" = 0 ] && tag="REMOVABLE?"            # HEAD already inside a canonical branch
  [ "$uniq" != 0 ] && ! held "$head" && tag="UNPROTECTED" # nothing else points at these commits: archive first
  is_open "${br:-}" && tag="OPEN-PR"
  [ "$dirty" != 0 ] && tag="DIRTY"                        # never remove; inspect and preserve
  printf '%-11s dirty=%-3s unique=%-3s %s  %s\n' "$tag" "$dirty" "$uniq" "$br" "$path"
done
printf '\n== local branches already merged into a canonical branch (candidates, verify before deleting)\n'
for c in "${CANON[@]}"; do git branch --format='%(refname:short)' --merged "$c"; done | sort -u |
  grep -vxE 'main|staging|staging-integration' || true
printf '\n== remote branches (excluding canonical)\n'
git branch -r --format='%(refname:short)' | grep -vE '^origin/(HEAD|main|staging|staging-integration)$' || true
