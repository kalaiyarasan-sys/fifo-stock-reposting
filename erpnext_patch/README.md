# ERPNext patch: early exit in reposting

`0001-repost-early-exit.patch` is a change to ERPNext **v15.110.0**. It touches one file and adds two:

| File | What |
|---|---|
| `erpnext/stock/stock_ledger.py` | The change, in `update_entries_after` (about 120 lines) |
| `erpnext/stock/tests/test_repost_early_exit.py` | Integration tests on the Milk / Milk Powder scenario |
| `erpnext/stock/tests/repost_early_exit_benchmark.py` | Compares a full repost with the early exit |

The design is explained in [DESIGN.md](../DESIGN.md#5-the-change-i-propose-in-erpnext).

## Apply it

Use a test site, not a live one.

```bash
cd ~/frappe-bench/apps/erpnext
git status                       # should be clean
git apply --check /path/to/0001-repost-early-exit.patch
git apply /path/to/0001-repost-early-exit.patch
```

To undo it later:

```bash
cd ~/frappe-bench/apps/erpnext
git apply -R /path/to/0001-repost-early-exit.patch
```

## Run the tests

```bash
cd ~/frappe-bench
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --module erpnext.stock.tests.test_repost_early_exit --skip-before-tests
```

`--skip-before-tests` keeps ERPNext from changing the site's defaults for its own test data.
The tests create their own items, supplier and customer in the default company. They need a fiscal
year that covers January 2026, and the `Stores` warehouse and `Nos` UOM that the setup wizard creates.

| Test | Checks |
|---|---|
| `test_task_scenario_values_after_rate_change` | All the task numbers after 60 is corrected to 80 with a Landed Cost Voucher |
| `test_early_exit_gives_same_ledger_as_full_repost` | Same ledger with and without the early exit, and the 40 later Milk entries skipped |
| `test_return_after_convergence_is_still_reposted` | A purchase return after the converged point is still recalculated |
| `test_bin_matches_last_entry_after_early_exit` | Bin qty and value equal the last ledger entry |

If other reposts are queued or failed on the site, the early exit stays off (see DESIGN.md), and the
tests that depend on it are skipped with a message.

## Run the benchmark

```bash
bench --site <site> execute erpnext.stock.tests.repost_early_exit_benchmark.run --kwargs "{'extra_days': 60}"
```

It builds the scenario twice, with 2 × `extra_days` normal Milk entries after the manufacture entry
(one per day from 22 Jan, so keep `extra_days` inside the fiscal year: 60 fits a year ending 31 March),
corrects the 10 Jan rate to 80, prints the entries written and the time taken, and checks both ledgers
are identical. Everything is rolled back at the end.

## Turn it off

```bash
bench --site <site> set-config disable_repost_early_exit 1
```

## Result on my site

ERPNext v15.110.0, with the patch: `Ran 4 tests ... OK`.

```
Later Milk entries after the manufacture entry: 120
Mode                    Recalculated   Skipped   Seconds
Full repost (today)              126         0      6.23
Early exit (patch)                 6       120      7.96
Both ledgers identical: yes
```

## Debugging on a real site

The first version passed the model tests but skipped nothing on ERPNext. The stats showed early exit
was on, with 46 entries processed and 0 skipped, and a trace showed the "recalculated" values were
always the old ones. The reason: `repost_stock_ledger_entry()` does `sle = frappe._dict(sle)` and
recalculates that **copy**, then keeps it in `prev_sle_dict`. The patch now reads the new values from
`prev_sle_dict`. The stats are recorded only when `frappe.flags.repost_early_exit_stats` is a list,
which the tests and the benchmark set.
