# Worktree cleanup, 2026-11-19

Proof of "merged": the branch tip SHA equals the head SHA of a MERGED pull request (file-content equivalence is not usable, because later PRs changed the same files). Each worktree was clean. An archive tag was pushed and verified equal to the tip before the worktree was removed without force. Branches were kept.

| Branch | PR | Tip | Archive tag |
|---|---|---|---|
| ai/embeddinggemma2-contract | #191 | c05b3f2a5 | archive/reconciliation/20261119-emb2-contract |
| fix/migration-downgrade-fixture | #185 | 2476c8dc6 | archive/reconciliation/20261119-migration-downgrade-fixture |
| feature/whatsapp-image-match | #175 | 66a2f1ff0 | archive/reconciliation/20261119-whatsapp-image-match |
| feature/whatsapp-model-assistant | #177 | 389b2a219 | archive/reconciliation/20261119-whatsapp-model-assistant |
| docs/issue-doc-reconciliation-20261108 | #194 | 80f135fbe | archive/reconciliation/20261119-docs-reconciliation-20261108 |

Left in place, with the reason:

- 10 `wt/t_*` worktrees: Kanban-owned.
- 7 detached QA worktrees: owners have not confirmed they are disposable.
- Dirty worktrees (uncommitted work): m4-provider-training-policy, m4-provider-training-policy-v2, local-ai-search-integration, local-ingestion-category-filter, local-multilingual-e5, docs-status-correction, elegance-m1-s3-admin-accounts, Elegance-Shawls-m1-s4.
- Clean worktrees whose tip does not equal a merged PR head (merged PR heads differ, PR closed, or no PR): pr-163-conflict-resolution (#165 head differs), pr-165-recovery (#166 closed), reconciliation-20261106 (#161 head differs), settings-test-fixture (#190 head differs), staging-migration-chain-0018 (#162 closed), migration-contract-0018, m4-batch-a-backend/frontend, m4-batch-a, m4-training-controls-rework, local-staging-1eb507f5, docs-fix-leaks. Possibly unique work: not removed, owner to confirm.
