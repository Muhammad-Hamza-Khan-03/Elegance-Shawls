# Repository hygiene: branches, worktrees and local artifacts

Short rules plus a repeatable audit for humans and agents. The release flow itself is in `docs/RELEASE_WORKFLOW.md`; this file is about keeping the repo from filling up with abandoned branches and worktrees.

## Rules

1. **One purpose and one owner per branch.** A task branch is cut from the latest `origin/integration`, named by its purpose, and owned by one person or Kanban task (put the task id or issue number in the PR).
2. **Short-lived.** Open the PR early. A branch with no PR and no commits for 7 days is a cleanup candidate, not a parking spot.
3. **Worktrees only when justified**: parallel work, or a dirty main checkout. Reuse an existing worktree for the same purpose before adding another. Disposable QA checkouts are `git worktree add --detach` and are removed when the verdict is recorded.
4. **Clean up after merge.** Once a PR is squash-merged and its checks are green, delete the remote branch (GitHub does this when "automatically delete head branches" is on; `gh pr merge --delete-branch` also does it), remove its worktree, delete the local branch.
5. **Never remove a dirty worktree, a worktree with a live process, or one a live Kanban task or open PR uses.** Never force-remove. Never `rm -rf` an unregistered directory without checking that it is not a standalone clone holding commits that exist nowhere else.
6. **Archive before retiring unmerged work.** Tag the tip `archive/<date>/<branch>`, push the tag, verify `git ls-remote` returns the same SHA, and only then delete the branch. Pushing a tag changes nothing else.
7. **Squash merges hide ancestry.** `git branch --merged` misses squash-merged branches. Prove "merged" by comparing the branch tip to the merged PR's `headRefOid` (`gh pr view <n> --json headRefOid`) or by tree equality (`git merge-tree --write-tree <base> <branch>` equals `<base>^{tree}`). A branch whose tip differs from its PR head has commits that were never reviewed: archive it.
8. **Deleting an ignored file is deleting data.** `git worktree remove` also deletes ignored files (`.env`, models, datasets, evidence). Before removing any worktree list `git status --porcelain --ignored -uall` and keep or move anything that is not a reproducible build artifact (`node_modules`, `.venv`, `__pycache__`, `.next`, test output, `*.tsbuildinfo`, `next-env.d.ts`).
9. **Permanent branches are `main`, `staging`, `integration`.** Never delete, reset or force-push them.
10. **Keep Kanban, issues and PRs in sync.** A Kanban task that is `done` or `archived` no longer protects its workspace; one that is `blocked` or `todo` still does. When you retire a branch, comment on the issue or task with the archive tag.

## Audit procedure (about five minutes)

```bash
scripts/repo_audit.sh            # read-only: worktrees (dirty / unique commits / open PR) and merged-branch candidates
```

The script cannot see Hermes Kanban or running processes. Before removing anything it lists, also check:

```bash
# running processes whose cwd is inside a worktree
for p in $(ps -eo pid --no-headers); do readlink /proc/$p/cwd; done 2>/dev/null | sort -u | grep -F worktrees
# Kanban tasks that still own a workspace (read-only)
sqlite3 -readonly ~/.hermes/kanban/boards/elegance-shawls/kanban.db \
  "select id,status,workspace_path from tasks where status not in ('done','archived') and workspace_path is not null"
gh pr list --state open --json number,headRefName,baseRefName
```

Then, per candidate:

1. Skip anything dirty, in use, owned by a live Kanban task, backing an open PR, or touched in the last 12 hours (another agent may be mid-task).
2. Confirm its HEAD is held by a branch or tag (`git branch -a --contains <sha>`). If not, tag it `archive/<date>/<name>` and push the tag.
3. Scan ignored files (rule 8).
4. `git worktree remove <path>` (never `--force`), then `git worktree prune`.
5. Delete a local branch only when it is an ancestor of a canonical branch, equals a merged PR's head, or is archived and superseded. Record `branch sha` in a log first so it can be recreated: `git branch <name> <sha>`.
6. Take a backup first: `git bundle create ~/archive/<date>/all-refs.bundle --all && git bundle verify <that file>`.

## Branch names

The development branch is `integration`. It was called `staging-integration` until 2026-11-06 because an `integration/...` ref occupied the namespace (git cannot hold `integration` and `integration/x` together). That ref was fully merged and retired, the branch was recreated at the same commit as `integration` (no history rewritten), and CI triggers, branch protection, open PR bases, docs and agent instructions were moved before the old name was retired. Never create an `integration/...` branch; use `integration-<topic>` or a type prefix (`feature/`, `fix/`, `ai/`, ...).
