import unittest

from fifo_repost import FIFOQueue, NegativeStockError


class TestFIFOQueue(unittest.TestCase):
	def test_oldest_layer_goes_out_first(self):
		queue = FIFOQueue([[100, 50], [50, 60]])
		self.assertEqual(queue.remove(80), 4000)
		self.assertEqual(queue.state(), ((20, 50), (50, 60)))

	def test_remove_across_layers(self):
		queue = FIFOQueue([[20, 50], [50, 80], [50, 60]])
		self.assertEqual(queue.remove(100), 20 * 50 + 50 * 80 + 30 * 60)
		self.assertEqual(queue.state(), ((20, 60),))

	def test_same_rate_is_merged_into_last_layer(self):
		queue = FIFOQueue([[20, 50], [50, 60]])
		queue.add(50, 60)
		self.assertEqual(queue.state(), ((20, 50), (100, 60)))

	def test_outgoing_rate_uses_matching_layer_first(self):
		queue = FIFOQueue([[20, 50], [50, 80]])
		self.assertEqual(queue.remove(5, outgoing_rate=80), 400)
		self.assertEqual(queue.state(), ((20, 50), (45, 80)))

	def test_cannot_remove_more_than_stock(self):
		with self.assertRaises(NegativeStockError):
			FIFOQueue([[10, 50]]).remove(11)


if __name__ == "__main__":
	unittest.main()
