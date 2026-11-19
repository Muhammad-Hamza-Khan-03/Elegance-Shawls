# Review rubric for evaluation rows

Decide each row independently, then write `accept`, `reject` or `correct` (with the corrected value).

| Check | accept when | otherwise |
|---|---|---|
| Language | the `lang` label is right (en, ur = Urdu script, roman_ur = Roman Urdu, mixed) | `correct` the label |
| Natural phrasing | a shopper in Pakistan could plausibly type or say it (for voice rows: plausibly spoken) | `reject` if it reads like machine-made or vocabulary-table output |
| Intent and label | the expected category / colour / material / price / negation matches what the words mean | `correct` if one value is wrong; `reject` if the meaning is ambiguous or unanswerable as labelled |
| Spelling variants | the spelling is one real people use (shaal / shal / chaadar all fine) | `correct` obvious typos that change meaning |
| Negation and price | "not red", "under 4000", "kam se kam 2000" are labelled exactly as spoken | `correct` |
| Personal data | none | `reject` and tell the owner; such a row must never enter the repository |

Record uncertainty in `note` instead of guessing. A row you cannot judge is `reject` with a note, not `accept`.
