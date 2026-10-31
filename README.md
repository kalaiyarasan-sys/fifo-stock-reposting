# FIFO Stock Reposting

My solution to the **Stock Reposting and Valuation** task: Milk and Milk Powder with FIFO, where the
10 Jan Purchase Receipt is corrected from ₹60 to ₹80.

It has two parts:

1. **A change to ERPNext** (`erpnext_patch/`). ERPNext's repost recalculates and rewrites every later
   stock ledger entry, even after the values stop changing. The patch stops an item-warehouse once
   its FIFO state is back to what is stored. It has integration tests on the task scenario.
2. **A small model** (`fifo_repost/`) of the same reposting logic in plain Python, with 25 tests.
   It explains the logic without needing a Frappe site.

The answers to the four questions and the design are in **[DESIGN.md](DESIGN.md)**.

> Version 1 of this repository, as first submitted, is the release
> [`submitted-v1`](https://github.com/kalaiyarasan-sys/fifo-stock-reposting/releases/tag/submitted-v1). [CHANGELOG.md](CHANGELOG.md) lists what changed.

## Result

| Transaction | Before (₹60) | After (₹80) |
|---|---|---|
| PR 10 Jan, Milk +50 | balance 8,000 | balance **9,000** |
| DN 15 Jan, Milk −80 | cost 4,000 | cost **4,000** (FIFO uses the opening layer @ 50) |
| PR 20 Jan, Milk +50 | balance 7,000 | balance **8,000** |
| Manufacture 21 Jan, Milk −100 | cost 5,800 | cost **6,800** (20×50 + 50×80 + 30×60) |
| Manufacture 21 Jan, Milk Powder +10 | 580 / kg | **680 / kg** |
| DN 25 Jan, Milk Powder −10 | cost 5,800 | cost **6,800** |
| Milk left | 20 L = 1,200 | 20 L = 1,200 |

These match what I got on an ERPNext v15 site ([screenshots](docs/screenshots/)).

After the 21 Jan manufacture entry the Milk queue is `[20 @ 60]` before and after the change.
So every later Milk entry would be recalculated to the same values. The early exit skips them.

Measured on my ERPNext v15.110.0 site with the patch, with 120 normal Milk entries after 21 Jan
([screenshot](docs/screenshots/08-benchmark-on-erpnext.png)):

| Mode | Stock entries recalculated | Skipped | Seconds (whole LCV submit) | Ledger |
|---|---|---|---|---|
| Full repost (today) | 126 | 0 | 6.23 | |
| Early exit (patch) | **6** | **120** | 7.96 | identical |

The patch removes 120 of 126 stock ledger rewrites. The total time did not go down in this run:
it is the whole Landed Cost Voucher submit, and most of it is the GL repost, which still reposts
every later voucher (see [DESIGN.md](DESIGN.md#what-it-does-and-does-not-save)). One run of a few
seconds is also noisy. So the result I can claim is fewer database writes with the same ledger,
not a faster repost yet.

All 4 ERPNext integration tests pass on the same site.

## Run the model

Python 3.8 or later. No other packages are needed.

```bash
python -m fifo_repost.scenario        # prints the ledger before and after the change
python -m unittest -v                 # 25 tests
```

`pytest` also works: `pip install -r requirements-dev.txt` then `pytest -v`.

## Try the ERPNext change

On an ERPNext **v15.110.0** test site:

```bash
cd ~/frappe-bench/apps/erpnext
git apply /path/to/erpnext_patch/0001-repost-early-exit.patch

cd ~/frappe-bench
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --module erpnext.stock.tests.test_repost_early_exit --skip-before-tests
bench --site <site> execute erpnext.stock.tests.repost_early_exit_benchmark.run --kwargs "{'extra_days': 60}"
```

Details are in [erpnext_patch/README.md](erpnext_patch/README.md).

## Layout

```
erpnext_patch/
  0001-repost-early-exit.patch   change to erpnext/stock/stock_ledger.py + tests + benchmark
  README.md                      how to apply, test and turn it off
fifo_repost/
  fifo.py                        FIFO queue (like FIFOValuation)
  ledger.py                      entries, repost with dependants and early exit
  scenario.py                    the task scenario
tests/
  test_fifo.py                   the queue
  test_repost.py                 task numbers, early exit, ordering, errors
docs/screenshots/                the scenario on an ERPNext v15 site
DESIGN.md                        answers to the questions and the design
CHANGELOG.md
```
