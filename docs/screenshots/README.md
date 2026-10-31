# Screenshots

The scenario recreated on an ERPNext v15 site (company "Test", items `RM-1001-MILK` and
`FG-2001-MILK-POWDER`).

| File | Shows |
|---|---|
| `01-stock-ledger-before.png` | Stock Ledger before the change: Manufacture Milk 5,800, Milk Powder 580 |
| `02-stock-ledger-before-values.png` | Same report, value columns |
| `03-cancel-blocked.png` | Cancelling the 10 Jan receipt is refused: 30 L of Milk needed on 21 Jan |
| `04-negative-stock-warning.png` | ERPNext's warning that negative stock disables FIFO |
| `05-purchase-receipts.png` | Cancelled receipt at ₹3,000 and the amended one at ₹4,000 |
| `06-stock-ledger-after.png` | Stock Ledger after the repost |
| `07-stock-ledger-after-values.png` | Value columns after: Milk 6,800, Milk Powder 680, DN 6,800 |
| `08-benchmark-on-erpnext.png` | Benchmark with the patch: 126 entries recalculated without it, 6 with it, ledgers identical |
