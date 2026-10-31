# Changelog

## v2

Added after the first submission, which is kept as the release `submitted-v1`.

- **ERPNext change** (`erpnext_patch/`): early exit in `update_entries_after.repost_stock_ledgers()`
  for ERPNext v15.110.0. An item-warehouse whose recalculated state matches the stored state again is
  not recalculated or written any further. Includes safety rules, a site config switch to turn it
  off, integration tests on the task scenario and a benchmark.
- **Model rebuilt** to match ERPNext's shape: entries per item **and warehouse**, ordered by posting
  date-time and creation, dependants for manufacture, returns that take their rate from the receipt,
  a Bin, and the same early exit.
- **Fixed:** a finished good got a rate of 0 when its row was created before the consumption row of
  the same manufacture entry. Produced rows now always come after the rows their rate comes from.
- **Fixed:** the repost replayed every item from the changed date. It now reposts only the changed
  item-warehouse and the items that depend on it.
- `RepostResult` now reports which entries were recalculated, skipped, and changed in value
  (the vouchers that need a GL repost).
- Tests: 11 → 25 in the model, plus ERPNext integration tests. They use `unittest`, so they run without
  installing anything; `pytest` also runs them.
- Docs: DESIGN.md with the ERPNext reposting flow, the proposed change and how I would handle the
  correction on a live site. Screenshots of the scenario on an ERPNext v15 site.
- Tested on ERPNext v15.110.0: all 4 integration tests pass; with 120 later entries the patch
  recalculates 6 instead of 126 with an identical ledger (total time not lower, see README).
- Removed `Test_Cases.xlsx`; the test cases are listed in DESIGN.md and the test names.

## v1 — submitted-v1

Standalone FIFO ledger with reposting, 11 tests and answers to the four questions.
