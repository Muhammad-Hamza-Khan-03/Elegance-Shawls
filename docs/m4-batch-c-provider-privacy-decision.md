# M4 Batch C provider privacy decision packet

**Task:** `t_m4c_provider_decision`
**Mode:** privacy-readiness only; no provider selected, no spend, no credentials, no live calls.
**Decision:** `BLOCKED_PROVIDER_PRIVACY_DECISION`

## Scope and non-negotiables

This packet compares only options with a verifiable no-training or self-hosted boundary. It does not recommend or activate a paid provider. Free-tier and opt-out-only claims are rejected. Customer memory remains disabled (`MEMORY_EXTRACTION_ENABLED=false` by default); PostgreSQL remains the sole application database.

## Candidate evidence matrix

| Option | Privacy boundary that can be verified | Retention/deletion evidence still required | Spend/approval status |
|---|---|---|---|
| OpenAI API business/API terms + eligible Zero Data Retention controls | Official API/business privacy materials state API inputs/outputs are not used to train by default; ZDR is endpoint/account eligibility, not assumed | Written account-level ZDR approval, abuse-monitoring retention, subprocessors/region, deletion and incident terms | **Not selected.** Paid account and any spend require Hamza approval |
| Anthropic commercial API | Official commercial/API terms and privacy documentation must be attached for the exact account and product; no inference from consumer plans | Written retention, training-use, subprocessors/region, deletion and security terms for the exact plan | **Not selected.** Paid account and any spend require Hamza approval |
| Self-hosted local model (for example a pinned Transformers snapshot) | No provider receives prompts; runtime can be offline with local files only and outbound sockets blocked | Model license, weight provenance, host access controls, disk/log retention, patching, deletion proof and resource budget | **Preferred evaluation path, not a selection.** No hosted spend |

### Verifiable references

- OpenAI API data/privacy overview: <https://openai.com/enterprise-privacy/> and <https://platform.openai.com/docs/models/how-we-use-your-data>.
- Anthropic commercial/API privacy: <https://www.anthropic.com/legal/commercial-terms> and <https://www.anthropic.com/legal/privacy>.
- Hugging Face Transformers offline/local-files operation: <https://huggingface.co/docs/transformers/v4.49.0/en/installation>.

References are evidence pointers, not approval. Provider terms change; an owner must re-check the exact account/contract immediately before any activation.

## Required decision record before promotion

1. Name one exact paid no-training account/contract **or** one self-hosted model snapshot and license.
2. Attach dated terms, retention/deletion behavior, region/subprocessor review, access controls, incident handling, and budget boundary.
3. Run the fail-closed configuration test: unknown/free/opt-out provider is refused; only explicit `no_training` or `self_hosted` passes.
4. Obtain named provider/privacy owner approval and Hamza's explicit approval before any paid account, spend, credential, or live request.

**Current owner approval:** absent. **Production activation:** blocked.
