# Design: Stock Reposting and Valuation (FIFO)

This document answers the four questions of the task and explains the code change I propose.
All ERPNext references are to **v15.110.0**.

## The scenario

Milk and Milk Powder, both FIFO, one warehouse. The 10 Jan receipt is corrected from ₹60 to ₹80.
I recreated it on an ERPNext v15 site first ([screenshots](docs/screenshots/)), and the model in
`fifo_repost/` gives the same numbers.

| Date | Transaction | Before (₹60) | After (₹80) |
|---|---|---|---|
| 01 Jan | Opening, Milk +100 @ 50 | balance 5,000 | balance 5,000 |
| 10 Jan | Purchase Receipt, Milk +50 | in 3,000, balance 8,000 | in **4,000**, balance **9,000** |
| 15 Jan | Delivery Note, Milk −80 | out 4,000, balance 4,000 | out 4,000, balance **5,000** |
| 20 Jan | Purchase Receipt, Milk +50 @ 60 | in 3,000, balance 7,000 | in 3,000, balance **8,000** |
| 21 Jan | Manufacture, Milk −100 | out 5,800, balance 1,200 | out **6,800**, balance 1,200 |
| 21 Jan | Manufacture, Milk Powder +10 | rate 580 | rate **680** |
| 25 Jan | Delivery Note, Milk Powder −10 | out 5,800 | out **6,800** |

The FIFO queue of Milk after the change:

```
10 Jan  [100 @ 50] [50 @ 80]
15 Jan  [ 20 @ 50] [50 @ 80]                 80 out from the oldest layer = 80 × 50 = 4,000
20 Jan  [ 20 @ 50] [50 @ 80] [50 @ 60]
21 Jan  [ 20 @ 60]                            100 out = 20×50 + 50×80 + 30×60 = 6,800
```

## 1. Which transactions are affected

Every stock ledger entry of **Milk in that warehouse dated on or after 10 Jan**, and every entry of an
item made from that Milk after that point.

| Entry | Affected | Why |
|---|---|---|
| Opening, 1 Jan | No | Before the change |
| PR 10 Jan | Yes, its value | This is the change |
| DN 15 Jan | Only its balance | FIFO took the 80 L from the opening layer @ 50, so its **cost does not change**. The stored balance and queue still change, because the 10 Jan layer is now @ 80 |
| PR 20 Jan | Only its balance | Its own rate is the same |
| Manufacture 21 Jan, Milk | Yes, its value | It consumes 50 L of the 10 Jan layer |
| Manufacture 21 Jan, Milk Powder | Yes, its rate | A different item. Its rate is the cost of the Milk consumed |
| DN 25 Jan, Milk Powder | Yes, its value | It sells Powder that now costs 680/kg |

Outside the stock ledger:

- **GL entries** change only for vouchers whose value changed: PR 10 Jan (+1,000 stock, against
  Stock Received But Not Billed or the landed cost account), the Manufacture entry (if Milk and Milk
  Powder use different stock accounts) and DN 25 Jan (+1,000 cost of goods sold). DN 15 Jan and
  PR 20 Jan need no GL change.
- **Bin** of Milk and of Milk Powder (current qty and value).
- **Stock Entry** rows: `basic_rate` of the Milk row and the valuation rate of the Powder row.

Two points that change the answer:

- **The valuation method.** With Moving Average the 15 Jan cost would also change (4,266.67 → 4,800),
  because the average rate after 10 Jan changes from 53.33 to 60.
- **Batches.** With batch-wise valuation, only the transactions that use the 10 Jan batch change.

## 2. How ERPNext recalculates

This is the flow in ERPNext v15.110.0.

| Step | Code | What it does |
|---|---|---|
| 1 | `StockController.repost_future_sle_and_gle()` | A back-dated submit, cancel or Landed Cost Voucher creates a **Repost Item Valuation** (RIV) |
| 2 | `repost_entries()` in `repost_item_valuation.py` | Hourly job. Takes queued RIVs ordered by posting date and time |
| 3 | `repost_future_sle()` in `stock_ledger.py` | For each item-warehouse of the voucher, creates `update_entries_after` |
| 4 | `update_entries_after.repost_stock_ledgers()` | Loads every later entry of that item-warehouse, ordered by `posting_datetime`, then `creation` |
| 5 | `process_sle()` → `update_queue_values()` | Starts from the previous entry's stored `stock_queue`, applies `FIFOValuation.add_stock` / `remove_stock`, and saves qty, value, rate and queue on the entry |
| 6 | `update_outgoing_rate_on_transaction()` | Writes the new outgoing rate back into the Delivery Note or Stock Entry row |
| 7 | `include_dependant_sle_in_reposting()` | The Milk row of the Manufacture entry has `dependant_sle_voucher_detail_no`, so the later entries of **Milk Powder** are added to the work queue |
| 8 | `update_bin()` | Bin = values of the last entry |
| 9 | `repost_gl_entries()` | Reposts GL for the vouchers found in step 3 to 7 |

The order matters: each entry starts from the state the previous entry left.

## 3. How I would design the reposting logic for FIFO

1. **Never in the user's request.** Queue the work, run it in the background, and show progress.
2. **Start from the changed point**, using the queue stored in the entry just before it.
   Never replay from the first transaction.
3. **Work per item-warehouse**, because the FIFO queue belongs to an item in a warehouse.
4. **Replay in a fixed order**: posting date and time, then creation.
   A produced row comes after the rows its rate comes from.
5. **Follow dependencies**: when a consumption row changes, add the items it produced
   (Manufacture, Repack) or received (transfers) to the work queue.
6. **Stop when nothing more can change** (early exit, below).
7. **Return what changed**, so only those vouchers get a GL repost.
8. **Survive failures**: commit in batches, save where it stopped, and resume from there.
   One repost per item-warehouse at a time.

ERPNext already does 1 to 5 and 8. This repository adds **6** to ERPNext, and shows **7** in the model.

## 4. Problems with a running balance in every Stock Ledger Entry

Each entry stores `qty_after_transaction`, `stock_value`, `valuation_rate` and `stock_queue`.
Each of these depends on all earlier entries.

| Problem | In this scenario |
|---|---|
| One old change rewrites every later entry | Correcting 10 Jan rewrites everything after it, to today |
| It gets slow as history grows | A busy item has thousands of entries after a back-dated change |
| Wrong values while the repost is queued | Until the hourly job runs, reports and the Bin show old values |
| New entries are posted from stale balances | A delivery posted while the repost is pending starts from the old queue |
| Half done after a failure | A timeout halfway leaves some entries new and some old (ERPNext resumes from the last saved point) |
| The change spreads to other items | Milk → Milk Powder, and transfers to other warehouses, so the size of the work is hard to know |
| Stock and GL drift | If the GL repost fails, stock value and the stock account do not match |
| Cancel and amend can be blocked | Cancelling the 10 Jan receipt was refused, because Milk would go 30 L negative on 21 Jan ([screenshot](docs/screenshots/)) |
| Closed periods change | Reports already filed for January would now show different numbers |
| Storage | The full queue is stored as JSON on every row |

The good side is that reading the stock on any date is one row, and the stored queue is a starting
point for reposting. So the stored balance should stay, but the cost of keeping it correct should be
lower. That is the change below.

## 5. The change I propose in ERPNext

### The problem in the code

`repost_stock_ledgers()` loops until the work queue is empty. For every later entry, `process_sle()`
recalculates it, writes the whole row with `frappe.get_doc(sle).db_update()`, and writes the rate back
into the voucher. It does this **even when the result is the same as what is stored**.

In this scenario, after the 21 Jan manufacture entry the Milk queue is `[20 @ 60]`, both before and
after the change. So every later Milk entry, which could be thousands, is recalculated to exactly
the values it already has.

ERPNext already uses a similar idea in one place: `update_qty_in_future_sle()` stops shifting quantities
at the next Stock Reconciliation (`get_next_stock_reco()`). This change does the same for valuation:
when the state matches the stored state again, that point works like a reconciliation.

### The change

For each item-warehouse, compare the state after each recalculated entry with the state that was stored:

```
state = (qty_after_transaction, stock_value, valuation_rate, stock_queue)
```

1. The first time they **differ**, the change has reached this item-warehouse.
2. If, after that, they are **the same again**, the item-warehouse has **converged**.
3. Later entries of a converged item-warehouse are **not recalculated or written**. The stored entry is
   used as the previous entry for whatever comes next.

Why it is correct: before the change the stored ledger was consistent. Each stored entry was
calculated from the stored entry before it. If the new state after entry *k* equals the stored state
after entry *k*, then entry *k+1* gets the same input as before. If its own rate did not change, its
result is the same as before. By induction this holds for every later entry.

### Safety rules

| Rule | Reason |
|---|---|
| A match counts only after a difference | The entry of the voucher that started the repost (for example the receipt a Landed Cost Voucher changes) is written just before the repost, so it always matches. Converging on it would skip entries that are still old |
| Entries whose rate comes from another transaction are always recalculated: `recalculate_rate` rows (finished goods, transfer-in), returns, internal transfers, repack, Stock Reconciliation, receipts when "Set Landed Cost Based on Purchase Invoice Rate" is on | Their rate can change even if the state before them did not. If the result differs, the item-warehouse is no longer converged |
| Serial and batch items are not converged | Their valuation is kept per serial or batch, not only in the queue |
| Negative balances are not skipped | The FIFO queue behaves differently below zero |
| Off when another repost is queued, in progress or failed | After a repost, `deduplicate_similar_repost()` marks later queued reposts of the same item-warehouse as **Skipped**, because a full walk covered them. An early exit would not. A failed repost may also have left old values |
| Bin stays correct | `update_bin()` uses the last entry in `prev_sle_dict`. A skipped entry is put there, so the Bin gets the last entry of the ledger |
| Site config `disable_repost_early_exit` | To turn it off |

One thing I only found by running it on ERPNext: `repost_stock_ledger_entry()` recalculates a **copy**
of the row (`frappe._dict(sle)`) and keeps the copy in `prev_sle_dict`. Comparing against the original
row always showed "no change", so nothing was ever skipped. The new values are read from `prev_sle_dict`.

### What it does and does not save

- It helps **rate corrections**: Landed Cost Vouchers, a Purchase Invoice at a different rate,
  amending a rate. These usually converge once the corrected layer has been consumed.
- It does **not** help a back-dated change of **quantity**. That shifts the balance of every later
  entry, so the state never matches again. The model has a test for this.
- On my site, with 120 later Milk entries, it recalculated **6 entries instead of 126**, with an
  identical ledger. The total time of the Landed Cost Voucher submit did not go down (6.23 s full,
  7.96 s with the patch, one run each), because most of that time is the GL repost.
- It does not yet reduce the **GL repost**. `_get_directly_dependent_vouchers()` still reposts GL for every
  later voucher of the item-warehouse. The model returns the list of vouchers whose value changed. Passing
  that list to `repost_gl_entries()` would be the next step.

### Tests

| Where | What |
|---|---|
| `tests/` (model, runs anywhere) | 25 tests: task numbers before and after, FIFO queue, early exit gives the same ledger as a full repost, stops at the right entry, finished good still reposted, return after convergence recalculated, quantity change never converges, Bin, other warehouse untouched, ordering, negative stock, wrong inputs |
| `erpnext_patch/` (ERPNext integration) | Task numbers after a Landed Cost Voucher, same ledger with and without the early exit and the later entries skipped, return after convergence, Bin. Plus a benchmark. All 4 pass on ERPNext v15.110.0 |

## 6. How I would handle this on a live site

In ERPNext a submitted Purchase Receipt cannot be edited. When I tried Cancel → Amend on my site,
ERPNext refused: *"30.0 units of Milk needed in Stores on 21-01-2026 for Stock Entry Manufacture"*.
Allowing negative stock to get past it gave the warning that negative stock disables FIFO valuation.
So on a live site I would not do that.

| Reason for the wrong rate | What I would do |
|---|---|
| The supplier's bill is ₹80 | Turn on *Set Landed Cost Based on Purchase Invoice Rate* in Buying Settings and make the Purchase Invoice at ₹80 |
| Freight, loading or other costs | A Landed Cost Voucher of ₹1,000 on the receipt |
| A typing mistake, nothing consumed yet | Cancel and amend |

Before: check *Stock Frozen Up To* and closed accounting periods, and agree with accounts whether
January can change. If January is closed, post the difference in the current period instead.
After: check the Repost Item Valuation is Completed, compare with the Stock Ledger, and run
*Stock and Account Value Comparison*.

## 7. Design decisions in the model

| Decision | Reason |
|---|---|
| Same shape as ERPNext: item + warehouse, posting datetime, creation order, dependants, Bin | So the model explains the real code |
| `Entry.rate_source` (`own`, `produced`, `return`) | Makes it explicit which entries take their rate from another one |
| Produced rows sort after consumption rows at the same time | Version 1 gave the finished good a rate of 0 if its row was created first |
| Changes are atomic: a copy is restored on error | A small model has no database transaction |
| `RepostResult` returns processed, skipped and changed entries | Shows what an early exit saves and which vouchers need a GL repost |
| Standard library only | Runs anywhere with `python -m unittest` |
| Floats with rounding at 9 places, like the SLE columns | Enough for a model. ERPNext uses field precision |
