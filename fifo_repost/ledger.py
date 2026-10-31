"""A small stock ledger with FIFO reposting, shaped like ERPNext's.

ERPNext concepts and their names here:

    Stock Ledger Entry                      -> Entry
    FIFO queue per item + warehouse         -> FIFOQueue per (item, warehouse)
    posting_datetime, then creation         -> posting, seq
    dependant SLE (Manufacture -> FG)       -> rate_source = "produced"
    return rate taken from original voucher -> rate_source = "return"
    Bin                                     -> Ledger.bins
    update_entries_after.repost_stock_ledgers -> Ledger.repost

The repost walks the entries of the changed item-warehouse in order, adds the finished
goods of a Manufacture entry when it reaches it, and stops processing an item-warehouse
once its recalculated state is the same as the stored state again (early exit).
"""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from .fifo import PRECISION, FIFOQueue

OWN, PRODUCED, RETURN = "own", "produced", "return"


@dataclass
class Entry:
	item: str
	warehouse: str
	posting: datetime
	voucher_type: str
	voucher_no: str
	qty: float  # + incoming, - outgoing
	rate: float = 0.0  # incoming rate
	rate_source: str = OWN  # where an incoming or return rate comes from
	return_against: str | None = None
	seq: int = 0  # creation order

	# Stored values, written by the repost
	value_change: float = 0.0
	qty_after: float = 0.0
	value_after: float = 0.0
	queue: tuple = field(default_factory=tuple)

	@property
	def key(self) -> tuple[str, str]:
		return (self.item, self.warehouse)

	@property
	def sort_key(self) -> tuple:
		# A produced row is processed after the rows its rate comes from, even when it was
		# created first. (In version 1 this order came only from the creation order.)
		return (self.posting, self.rate_source == PRODUCED, self.seq)

	def state(self) -> tuple:
		"""Everything the next entry of the same item-warehouse depends on."""
		return (round(self.qty_after, PRECISION), round(self.value_after, 2), self.queue)

	@property
	def has_dynamic_rate(self) -> bool:
		"""The rate comes from another entry, so it can change even if the state before it did not."""
		return self.rate_source != OWN


@dataclass
class RepostResult:
	processed: list[Entry] = field(default_factory=list)
	skipped: list[Entry] = field(default_factory=list)
	changed: list[Entry] = field(default_factory=list)  # value_change differs: GL needs a repost

	@property
	def changed_vouchers(self) -> list[str]:
		return sorted({entry.voucher_no for entry in self.changed})


class Ledger:
	def __init__(self, early_exit: bool = True):
		self.entries: list[Entry] = []
		self.bins: dict[tuple[str, str], tuple[float, float]] = {}
		self.early_exit = early_exit

	# ---------------------------------------------------------------- posting

	def post(self, entry: Entry) -> RepostResult:
		"""Add an entry and repost from its posting time. Nothing is saved if it fails."""
		entry.seq = len(self.entries) + 1
		return self._atomic(lambda: self._add_and_repost(entry))

	def change_incoming_rate(self, voucher_no: str, item: str, new_rate: float) -> RepostResult:
		"""Correct the rate of an incoming entry (a rate amendment or landed cost)."""

		def change():
			entry = self.get(voucher_no, item)
			if entry.qty <= 0 or entry.rate_source != OWN:
				raise ValueError("Only the rate of a receipt can be changed")
			entry.rate = new_rate
			return self.repost(entry.item, entry.warehouse, entry.posting)

		return self._atomic(change)

	def _add_and_repost(self, entry: Entry) -> RepostResult:
		self.entries.append(entry)
		return self.repost(entry.item, entry.warehouse, entry.posting)

	def _atomic(self, action):
		backup = copy.deepcopy((self.entries, self.bins))
		try:
			return action()
		except Exception:
			self.entries, self.bins = backup
			raise

	# ---------------------------------------------------------------- reposting

	def repost(self, item: str, warehouse: str, from_posting: datetime) -> RepostResult:
		result = RepostResult()
		queues: dict[tuple, FIFOQueue] = {}
		last_entry: dict[tuple, Entry] = {}
		diverged, converged = set(), set()
		queued_keys = {(item, warehouse)}
		work = deque(self._entries_from(item, warehouse, from_posting))

		while work:
			entry = work.popleft()
			key = entry.key
			if key not in queues:
				queues[key] = self._queue_before(entry)

			if self.early_exit and key in converged and not entry.has_dynamic_rate:
				# Same state as stored, so this entry would come out the same. Trust it.
				queues[key] = FIFOQueue(entry.queue)
				last_entry[key] = entry
				result.skipped.append(entry)
				continue

			stored_state, stored_change = entry.state(), entry.value_change
			self._process(entry, queues[key])
			last_entry[key] = entry
			result.processed.append(entry)
			if round(entry.value_change, 2) != round(stored_change, 2):
				result.changed.append(entry)

			if entry.state() != stored_state:
				diverged.add(key)
				converged.discard(key)
			elif key in diverged:
				converged.add(key)

			# Manufacture: the finished good's rate comes from this consumption
			if entry.voucher_type == "Manufacture" and entry.qty < 0:
				for produced in self._produced_rows(entry.voucher_no):
					if produced.key not in queued_keys:
						queued_keys.add(produced.key)
						work.extend(self._entries_from(produced.item, produced.warehouse, produced.posting))
						work = deque(sorted(work, key=lambda e: e.sort_key))

		for key, entry in last_entry.items():
			self.bins[key] = (entry.qty_after, entry.value_after)
		return result

	def _process(self, entry: Entry, queue: FIFOQueue) -> None:
		if entry.rate_source == RETURN:
			# A return takes the rate of the voucher it is returned against
			entry.rate = self.get(entry.return_against, entry.item).rate
		elif entry.rate_source == PRODUCED:
			entry.rate = self._consumed_cost(entry.voucher_no) / entry.qty

		if entry.qty > 0:
			queue.add(entry.qty, entry.rate)
			entry.value_change = entry.qty * entry.rate
		else:
			outgoing_rate = entry.rate if entry.rate_source == RETURN else 0.0
			entry.value_change = -queue.remove(-entry.qty, outgoing_rate)

		entry.qty_after = queue.qty
		entry.value_after = queue.value
		entry.queue = queue.state()

	# ---------------------------------------------------------------- lookups

	def get(self, voucher_no: str, item: str) -> Entry:
		for entry in self.entries:
			if entry.voucher_no == voucher_no and entry.item == item:
				return entry
		raise ValueError(f"No entry for {voucher_no} / {item}")

	def _entries_from(self, item: str, warehouse: str, posting: datetime) -> list[Entry]:
		rows = [e for e in self.entries if e.key == (item, warehouse) and e.posting >= posting]
		return sorted(rows, key=lambda e: e.sort_key)

	def _queue_before(self, entry: Entry) -> FIFOQueue:
		earlier = [
			e for e in self.entries if e.key == entry.key and e.sort_key < entry.sort_key
		]
		if not earlier:
			return FIFOQueue()
		return FIFOQueue(max(earlier, key=lambda e: e.sort_key).queue)

	def _produced_rows(self, voucher_no: str) -> list[Entry]:
		return [e for e in self.entries if e.voucher_no == voucher_no and e.rate_source == PRODUCED]

	def _consumed_cost(self, voucher_no: str) -> float:
		return -sum(
			e.value_change for e in self.entries if e.voucher_no == voucher_no and e.qty < 0
		)
