# Known dataset issues (documented, not silently fixed)

Frozen gold data is pinned by `artifact_manifest.json`. A defect found in it is recorded here and corrected only through a reviewed
manifest change with a reason (issue #139 review workflow), never by editing the data quietly.

## fp-005 (`datasets/filter_parsing.jsonl`)
- Query: `pashmina shawl between 5000 and 9000`. Expected: `category=shawls, min_price=5000, max_price=9000`.
- The production parser also returns `materials: ['pashmina']`, which is correct for the query; the gold label omits it.
- Effect: `filter_parsing` exact_match is 0.941 (16/17) instead of 1.0. The suite still passes its 0.90 threshold, so the defect does not
  change the gate result, and it is not hidden by lowering any threshold.
- Status: OPEN, awaiting independent review. Not corrected here on purpose.
