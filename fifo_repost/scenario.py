"""The Milk / Milk Powder scenario from the task.

Run it with:  python -m fifo_repost.scenario
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .ledger import PRODUCED, Entry, Ledger

STORES = "Stores"


def at(day: int, month: int = 1) -> datetime:
	return datetime(2026, month, day, 10, 0)


def build_milk_scenario(early_exit: bool = True, extra_days: int = 0) -> Ledger:
	"""extra_days adds one receipt and one delivery of Milk per day after the manufacture entry,
	to stand for the normal transactions that come after a backdated change."""
	ledger = Ledger(early_exit=early_exit)
	post = ledger.post

	post(Entry("Milk", STORES, at(1), "Stock Entry", "OPENING", 100, 50))
	post(Entry("Milk", STORES, at(10), "Purchase Receipt", "PR-10JAN", 50, 60))
	post(Entry("Milk", STORES, at(15), "Delivery Note", "DN-15JAN", -80))
	post(Entry("Milk", STORES, at(20), "Purchase Receipt", "PR-20JAN", 50, 60))
	post(Entry("Milk", STORES, at(21), "Manufacture", "MFG-21JAN", -100))
	post(Entry("Milk Powder", STORES, at(21), "Manufacture", "MFG-21JAN", 10, rate_source=PRODUCED))
	post(Entry("Milk Powder", STORES, at(25), "Delivery Note", "DN-25JAN", -10))

	for day in range(extra_days):
		posting = at(22) + timedelta(days=day)
		post(Entry("Milk", STORES, posting, "Purchase Receipt", f"PR-EXTRA-{day}", 10, 60))
		post(Entry("Milk", STORES, posting, "Delivery Note", f"DN-EXTRA-{day}", -10))

	return ledger


def print_ledger(ledger: Ledger, title: str) -> None:
	print(f"\n{title}")
	print(f"{'Date':<8}{'Item':<13}{'Voucher':<11}{'Qty':>6}{'Value chg':>11}{'Bal qty':>9}{'Bal value':>11}  Queue")
	for e in sorted(ledger.entries, key=lambda e: e.sort_key):
		queue = ", ".join(f"{q:g}@{r:g}" for q, r in e.queue)
		print(
			f"{e.posting:%d %b}  {e.item:<13}{e.voucher_no:<11}{e.qty:>6g}"
			f"{e.value_change:>11g}{e.qty_after:>9g}{e.value_after:>11g}  [{queue}]"
		)


def main() -> None:
	ledger = build_milk_scenario()
	print_ledger(ledger, "Before: 10 Jan purchase at Rs 60")

	result = ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
	print_ledger(ledger, "After: 10 Jan purchase at Rs 80")
	print(f"\nVouchers whose value changed (need a GL repost): {', '.join(result.changed_vouchers)}")

	big = build_milk_scenario(extra_days=100)
	result = big.change_incoming_rate("PR-10JAN", "Milk", 80)
	print(
		f"\nWith 200 more Milk entries after 21 Jan: {len(result.processed)} entries recalculated, "
		f"{len(result.skipped)} skipped by the early exit."
	)


if __name__ == "__main__":
	main()
