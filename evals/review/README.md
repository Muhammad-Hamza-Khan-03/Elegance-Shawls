# Human review of evaluation data (issue #139)

**Status: no dataset in this repository has been reviewed with this procedure.** No signed review record exists (`evals/reviews/` is
empty) and none may be created by an AI assistant: the reviewer key is held by the human reviewer. A qualified, independent
Urdu / Roman Urdu reviewer has not been identified; that is an open blocker. Real customer queries are BLOCKED
(`evals/real_queries_status.md`). Read `evals/provenance.py` for what each review status means.

## Who may review
- Reads Urdu script and Roman Urdu fluently (as used for shopping queries in Pakistan), judged by the owner, who records the basis in the decisions file header (`qualification`).
- Did **not** write or generate the rows being reviewed (the author of a dataset can never be its independent reviewer; the tool refuses).
- For Urdu / Roman Urdu held-out evidence use **two** reviewers who work separately (blind to each other's decisions). One reviewer is enough for `dev` data; the agreement check applies when two files are given.

## Steps
1. **Export** the rows: `python evals/review.py export datasets/<file>.jsonl --out /tmp/packet.jsonl` (the packet must live outside `datasets/`). Each row gets a content-hash id.
2. **Review** every row against `RUBRIC.md` and write one decisions file per reviewer: first line `{"header": {"reviewer": "<name>", "qualification": "<basis>", "date": "YYYY-MM-DD"}}`, then one `{"id", "decision": "accept|reject|correct", "corrected"?, "note"?}` per row. Every row needs a decision.
3. **Check**: `python evals/review.py check datasets/<file>.jsonl --decisions <file>`. With two reviewers: `python evals/review.py agree --decisions a.jsonl --decisions b.jsonl` (Cohen's kappa; signing needs kappa >= 0.6).
4. **Resolve** rejects and disagreements by correcting the *data* in a normal reviewed PR (a changed row changes its id and the dataset hash, so the review must be redone on the corrected file). The tool will not sign while any `reject` stands.
5. **Sign** (reviewer key holder only; the key is never committed): `EVAL_REVIEWER_KEY=... python evals/review.py sign datasets/<file>.jsonl --decisions a.jsonl [--decisions b.jsonl] --author "<who wrote the data>" --split dev|held_out`. This writes `evals/reviews/<file>.json`.
6. **Declare** in a reviewed PR: change the dataset's entry in `evals/provenance.yaml` to `review: human_reviewed_verified` with reviewer, date and scope. `python evals/provenance.py` then verifies the signed record (it needs the reviewer key, so CI without the key will report the dataset as unverifiable: fail closed). Keep the decisions files with the PR description; they hold the evidence behind the signature.
7. Release evidence is a separate step: a held-out dataset still needs its own signed attestation and the owner's signed approval (`evals/attestation.py`).

## What a signature does and does not prove
It proves the holder of the reviewer key signed this dataset hash with these names. It does not prove the named person read the rows, reads Urdu, or was independent of the author; those rest on who holds the key and on the owner's judgement recorded in the header. There is no key rotation or revocation.

## Real customer queries (blocked)
See `evals/real_queries_status.md`. When, and only when, the owner has changed that status deliberately: collect with consent, scrub (names, phone numbers, addresses, order references), load through `evals/intake.py` (which refuses while blocked and rejects rows that still look like personal data), declare the file in `provenance.yaml` with `origin: real_scrubbed`, then review it with the steps above. Never commit unscrubbed text.
