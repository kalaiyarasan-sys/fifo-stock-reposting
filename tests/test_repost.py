import unittest

from fifo_repost import RETURN, Entry, Ledger, NegativeStockError
from fifo_repost.scenario import STORES, at, build_milk_scenario


def values(ledger):
	"""The stored values of every entry, in ledger order, to compare two ledgers."""
	return [
		(e.voucher_no, e.item, round(e.value_change, 2), round(e.qty_after, 6), round(e.value_after, 2), e.queue)
		for e in sorted(ledger.entries, key=lambda e: e.sort_key)
	]


class TestTaskScenario(unittest.TestCase):
	def test_values_before_the_change(self):
		ledger = build_milk_scenario()
		self.assertEqual(ledger.get("DN-15JAN", "Milk").value_change, -4000)
		self.assertEqual(ledger.get("PR-20JAN", "Milk").value_after, 7000)
		self.assertEqual(ledger.get("MFG-21JAN", "Milk").value_change, -5800)
		self.assertEqual(ledger.get("MFG-21JAN", "Milk Powder").rate, 580)
		self.assertEqual(ledger.get("DN-25JAN", "Milk Powder").value_change, -5800)

	def test_values_after_rate_changed_to_80(self):
		ledger = build_milk_scenario()
		ledger.change_incoming_rate("PR-10JAN", "Milk", 80)

		self.assertEqual(ledger.get("PR-10JAN", "Milk").value_after, 9000)
		dn = ledger.get("DN-15JAN", "Milk")
		self.assertEqual(dn.value_change, -4000)  # FIFO took the opening layer @ 50
		self.assertEqual(dn.value_after, 5000)
		self.assertEqual(dn.queue, ((20, 50), (50, 80)))
		self.assertEqual(ledger.get("PR-20JAN", "Milk").value_after, 8000)
		self.assertEqual(ledger.get("MFG-21JAN", "Milk").value_change, -6800)  # 20@50 + 50@80 + 30@60
		self.assertEqual(ledger.get("MFG-21JAN", "Milk Powder").rate, 680)
		self.assertEqual(ledger.get("DN-25JAN", "Milk Powder").value_change, -6800)

	def test_vouchers_that_need_a_gl_repost(self):
		result = build_milk_scenario().change_incoming_rate("PR-10JAN", "Milk", 80)
		# DN-15JAN and PR-20JAN get a new balance but their value did not change
		self.assertEqual(result.changed_vouchers, ["DN-25JAN", "MFG-21JAN", "PR-10JAN"])

	def test_opening_stock_is_not_touched(self):
		ledger = build_milk_scenario()
		result = ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
		self.assertNotIn("OPENING", [e.voucher_no for e in result.processed])

	def test_final_milk_stock_is_same(self):
		ledger = build_milk_scenario()
		ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
		self.assertEqual(ledger.bins[("Milk", STORES)], (20, 1200))

	def test_rate_decrease(self):
		ledger = build_milk_scenario()
		ledger.change_incoming_rate("PR-10JAN", "Milk", 40)
		self.assertEqual(ledger.get("MFG-21JAN", "Milk").value_change, -4800)
		self.assertEqual(ledger.get("MFG-21JAN", "Milk Powder").rate, 480)

	def test_repost_twice_gives_same_result(self):
		ledger = build_milk_scenario()
		ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
		first = values(ledger)
		ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
		self.assertEqual(values(ledger), first)

	def test_changing_last_purchase_does_not_change_earlier_entries(self):
		ledger = build_milk_scenario()
		result = ledger.change_incoming_rate("PR-20JAN", "Milk", 70)
		self.assertNotIn("DN-15JAN", [e.voucher_no for e in result.processed])
		self.assertEqual(ledger.get("MFG-21JAN", "Milk").value_change, -6100)  # 20@50 + 50@60 + 30@70

	def test_balance_value_matches_queue(self):
		ledger = build_milk_scenario(extra_days=5)
		ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
		for entry in ledger.entries:
			self.assertAlmostEqual(entry.value_after, sum(q * r for q, r in entry.queue))


class TestEarlyExit(unittest.TestCase):
	def test_same_ledger_as_full_repost(self):
		full = build_milk_scenario(early_exit=False, extra_days=30)
		early = build_milk_scenario(early_exit=True, extra_days=30)
		full_result = full.change_incoming_rate("PR-10JAN", "Milk", 80)
		early_result = early.change_incoming_rate("PR-10JAN", "Milk", 80)

		self.assertEqual(values(full), values(early))
		self.assertEqual(len(full_result.processed), 66)
		self.assertEqual(len(early_result.processed), 6)
		self.assertEqual(len(early_result.skipped), 60)

	def test_stops_where_the_queue_is_back_to_stored(self):
		ledger = build_milk_scenario(extra_days=3)
		result = ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
		# MFG-21JAN Milk leaves [20 @ 60], same as before the change, so later Milk is skipped
		self.assertEqual(result.skipped[0].voucher_no, "PR-EXTRA-0")
		self.assertTrue(all(e.item == "Milk" for e in result.skipped))

	def test_finished_good_is_still_reposted(self):
		ledger = build_milk_scenario(extra_days=10)
		result = ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
		processed = {(e.voucher_no, e.item) for e in result.processed}
		self.assertIn(("MFG-21JAN", "Milk Powder"), processed)
		self.assertIn(("DN-25JAN", "Milk Powder"), processed)

	def test_return_after_convergence_is_recalculated(self):
		"""A purchase return takes its rate from the receipt, so the early exit must not skip it."""

		def build(early_exit):
			ledger = build_milk_scenario(early_exit=early_exit, extra_days=5)
			ledger.post(
				Entry("Milk", STORES, at(23), "Purchase Receipt", "PR-RET", -5,
					rate_source=RETURN, return_against="PR-10JAN")
			)
			return ledger

		full, early = build(False), build(True)
		full.change_incoming_rate("PR-10JAN", "Milk", 80)
		result = early.change_incoming_rate("PR-10JAN", "Milk", 80)

		self.assertEqual(values(full), values(early))
		skipped = [e.voucher_no for e in result.skipped]
		self.assertIn("PR-EXTRA-0", skipped)  # Milk had converged before the return
		self.assertIn("PR-RET", [e.voucher_no for e in result.processed])

	def test_quantity_change_never_converges(self):
		"""A backdated receipt shifts the quantity of every later entry, so nothing is skipped."""
		ledger = build_milk_scenario(extra_days=5)
		result = ledger.post(Entry("Milk", STORES, at(12), "Purchase Receipt", "PR-12JAN", 10, 55))
		self.assertEqual(result.skipped, [])

	def test_bin_matches_last_entry(self):
		ledger = build_milk_scenario(extra_days=10)
		ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
		last = max((e for e in ledger.entries if e.item == "Milk"), key=lambda e: e.sort_key)
		self.assertEqual(ledger.bins[("Milk", STORES)], (last.qty_after, last.value_after))

	def test_other_warehouse_is_not_touched(self):
		ledger = build_milk_scenario()
		ledger.post(Entry("Milk", "Store 2", at(11), "Purchase Receipt", "PR-W2", 30, 55))
		ledger.post(Entry("Milk", "Store 2", at(16), "Delivery Note", "DN-W2", -10))
		result = ledger.change_incoming_rate("PR-10JAN", "Milk", 80)
		self.assertNotIn("Store 2", {e.warehouse for e in result.processed})


class TestOrderingAndErrors(unittest.TestCase):
	def test_produced_row_created_before_consumption_gets_correct_rate(self):
		"""Version 1 gave the finished good a rate of 0 when its row was created first."""
		ledger = Ledger()
		ledger.post(Entry("Milk", STORES, at(1), "Stock Entry", "OP", 100, 50))
		ledger.post(Entry("Milk Powder", STORES, at(21), "Manufacture", "MFG", 10, rate_source="produced"))
		ledger.post(Entry("Milk", STORES, at(21), "Manufacture", "MFG", -100))
		self.assertEqual(ledger.get("MFG", "Milk Powder").rate, 500)

	def test_backdated_purchase_changes_later_cost(self):
		ledger = Ledger()
		ledger.post(Entry("Milk", STORES, at(10), "Purchase Receipt", "PR-1", 50, 60))
		ledger.post(Entry("Milk", STORES, at(15), "Delivery Note", "DN-1", -30))
		self.assertEqual(ledger.get("DN-1", "Milk").value_change, -1800)

		ledger.post(Entry("Milk", STORES, at(5), "Purchase Receipt", "PR-0", 20, 40))  # entered late
		self.assertEqual(ledger.get("DN-1", "Milk").value_change, -(20 * 40 + 10 * 60))

	def test_cannot_deliver_more_than_stock(self):
		ledger = build_milk_scenario()
		before = values(ledger)
		with self.assertRaises(NegativeStockError):
			ledger.post(Entry("Milk", STORES, at(26), "Delivery Note", "DN-BIG", -500))
		self.assertEqual(values(ledger), before)  # nothing half saved

	def test_cannot_change_rate_of_delivery_or_finished_good(self):
		ledger = build_milk_scenario()
		for voucher, item in (("DN-15JAN", "Milk"), ("MFG-21JAN", "Milk Powder"), ("NOT-THERE", "Milk")):
			with self.assertRaises(ValueError):
				ledger.change_incoming_rate(voucher, item, 80)


if __name__ == "__main__":
	unittest.main()
