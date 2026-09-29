# ADR 0004: Hybrid retrieval and scoring for name matching

## Status

Accepted

## Context

Sanctioned individuals and entities appear in customer data under
transliteration variants, reordered tokens, dropped middle names, typos and
added or removed honorifics. A single matching technique consistently fails
somewhere: exact or token-overlap matching misses typos and transliteration;
pure edit-distance or trigram similarity misses cases where tokens are
reordered or one is dropped; a single fuzzy ratio (e.g. token_set_ratio
alone) cannot be pushed to a high threshold without losing recall on true
matches, because it scores many unrelated names in the same high range.

## Decision

Union three independent retrievers for candidate generation (blocking),
scored by a single weighted composite function:

1. Token inverted index (GIN `&&` on `sanctions_names.tokens`), ranked by
   IDF-weighted overlap and restricted to the query's rarer tokens.
2. Trigram similarity (`pg_trgm`, `%` operator against the GIN trigram index).
3. Vector nearest neighbor (HNSW, cosine distance) on multilingual sentence
   embeddings.

A phonetic-key filter is added as a fourth, cheap retriever for short names
(two tokens or fewer), where the other three retrievers are least reliable.

Composite score = 0.35 x token_set_ratio + 0.25 x token_sort_ratio + 0.25 x
Jaro-Winkler (on sorted token keys) + 0.15 x embedding cosine similarity,
adjusted for missing rare tokens, weak-AKA capping, and secondary attributes
(date of birth, nationality, exact ID match, entity type).

## Rationale

- Each retriever covers a different failure mode of the others: token
  overlap survives typos in other tokens; trigram similarity survives typos
  within a token and minor reordering; vector similarity survives
  transliteration variants the equivalence table does not enumerate.
- Blocking on the query's rarest tokens (IDF-weighted, see
  `backend/app/services/screening/candidates.py:token_candidates`) rather
  than any shared token was a fix made after measuring, not a design
  guess: a query built entirely from common tokens (e.g. a bare legal
  suffix such as "SA") was pulling in every name sharing that token, tens
  of thousands of rows for the most common tokens in this dataset, and one
  such query drove single-screening p95 latency from under 300 ms to over
  1.7 seconds. Restricting blocking to the selective tokens (falling back to
  all tokens only when every token is common) and capping the pool fixed
  it without changing match quality.
- A second real defect was found the same way: `pg_trgm` only uses its GIN
  index for the `%` operator (with the threshold read from the
  `pg_trgm.similarity_threshold` GUC), not for `similarity(a, b) > x` written
  directly in a WHERE clause. The latter forced a full sequential scan;
  switching to `%` with `SET LOCAL pg_trgm.similarity_threshold` cut that
  retriever's latency roughly tenfold. See the measurements in
  `backend/app/services/screening/candidates.py:trigram_candidates`.
- The evaluation harness (`backend/app/services/screening/evaluate.py`)
  confirms the practical benefit of combining retrieval and scoring this
  way rather than using rapidfuzz alone: at the default Review threshold
  (72), recall is 99.5 percent (about 220 true matches out of 221, only 1
  false negative) versus 95.0 percent for a `token_set_ratio`-only baseline
  over the same candidate pool. More significantly, the hybrid pipeline can
  be pushed to a threshold (90) that still holds recall at 98.2 percent
  while cutting the false positive rate to 2.2 percent; the baseline's false
  positive rate never drops below roughly 46 percent at any threshold,
  because `token_set_ratio` alone cannot separate true matches from
  lookalikes once their scores are inflated by shared common tokens. See
  `docs/evaluation/report.md` for the full threshold sweep.

## Consequences

- Every screening query issues up to four retrieval queries plus a
  per-candidate scoring pass; this is the majority of the roughly 65-180 ms
  typical single-screening latency measured against the full ~44,000-name
  SDN dataset (`tests/integration/test_screening_performance.py`), comfortably
  under the 300 ms p95 target but not free.
- Retrieval and scoring both depend on `sanctions_token_stats` being kept
  current; it must be refreshed whenever the sanctions list is reloaded (the
  ingestion pipeline should call `refresh_token_idf` after `sdn_loaded`, or
  IDF weighting degrades to a uniform default and blocking falls back to
  unrestricted token overlap).
- The weights and adjustment magnitudes live in `risk_config.weights`
  (versioned) rather than only in code, so they can be retuned per the
  evaluation harness without a deployment, but the retrieval strategy itself
  (which techniques run, in what order) is code, since it is an engineering
  decision, not a compliance policy.
