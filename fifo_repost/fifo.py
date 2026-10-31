"""FIFO valuation queue.

Each layer is [qty, rate]. Stock comes in at the back and goes out from the front,
so the oldest stock is used first. Same idea as FIFOValuation in erpnext/stock/valuation.py.
"""

from __future__ import annotations

PRECISION = 9


class NegativeStockError(ValueError):
	pass


class FIFOQueue:
	def __init__(self, layers=None):
		self.layers = [[qty, rate] for qty, rate in (layers or [])]

	def add(self, qty: float, rate: float) -> None:
		if self.layers and self.layers[-1][1] == rate:
			self.layers[-1][0] += qty  # same rate as the last layer, merge it
		else:
			self.layers.append([qty, rate])

	def remove(self, qty: float, outgoing_rate: float = 0.0) -> float:
		"""Take qty from the oldest layers and return the cost of what was taken.

		Like ERPNext's FIFOValuation.remove_stock, when an outgoing rate is given (a return to
		the supplier) the layer with that rate is used first."""
		if qty > self.qty + 1e-9:
			raise NegativeStockError(f"Not enough stock: need {qty:g}, have {self.qty:g}")

		cost = 0.0
		while qty > 1e-9:
			index = 0
			if outgoing_rate > 0:
				index = next((i for i, (_, rate) in enumerate(self.layers) if rate == outgoing_rate), 0)
			layer = self.layers[index]
			taken = min(layer[0], qty)
			cost += taken * layer[1]
			layer[0] -= taken
			qty -= taken
			if layer[0] <= 1e-9:
				self.layers.pop(index)
		return cost

	@property
	def qty(self) -> float:
		return sum(qty for qty, _ in self.layers)

	@property
	def value(self) -> float:
		return sum(qty * rate for qty, rate in self.layers)

	def state(self) -> tuple:
		"""Rounded copy of the layers, used to compare two queues."""
		return tuple((round(qty, PRECISION), round(rate, PRECISION)) for qty, rate in self.layers)

	def copy(self) -> FIFOQueue:
		return FIFOQueue(self.layers)
