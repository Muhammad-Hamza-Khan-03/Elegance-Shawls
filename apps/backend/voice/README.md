# M5-S1 voice evaluation contract

This package is a provider-independent, deterministic contract boundary. It accepts a transient
`VoiceInput` and returns typed transcript/intent metadata; it does not perform ASR, call a model,
upload audio, or persist raw audio. `FakeVoiceProvider` is the only provider seam in this slice.

Normalization supports Urdu digits, common PKR spellings (`روپے`, `rupay`, `pkr`) and explicit
negation (`نہیں`, `نہ`, `nahi`, `nahin`, `mat`). Ambiguous prices and low-confidence inputs fail
closed with `needs_review=True`.

The evaluation score is exactly the arithmetic mean of per-example exact PKR-price correctness and
per-example exact negation correctness. WER is intentionally not used. The synthetic reviewed
fixture and checksum are validated by `python evals/voice_urdu_eval.py --release-ready`; an empty,
unreviewed, checksum-invalid, or failed evaluation blocks readiness.
