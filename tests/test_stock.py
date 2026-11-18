import os
import tempfile
import unittest

from tillpoint import db
from tillpoint.catalog import Catalog, OutOfStock


class TwoWorkerStockTest(unittest.TestCase):
    def test_second_worker_cannot_sell_stock_it_still_has_cached(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        first = db.connect(path)
        second = db.connect(path)
        try:
            Catalog(first).add_product("MUG", "Mug", 1200, stock=1)
            other = Catalog(second)
            self.assertEqual(other.get_product("MUG").stock, 1)
            Catalog(first).reserve("MUG", 1)
            with self.assertRaises(OutOfStock):
                other.reserve("MUG", 1)
            left = first.execute("SELECT stock FROM products WHERE sku = 'MUG'").fetchone()["stock"]
            self.assertEqual(left, 0)
        finally:
            first.close()
            second.close()
            os.remove(path)
