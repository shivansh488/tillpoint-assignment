import unittest

from tillpoint import db
from tillpoint.api import App


class CancelPendingTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect()
        self.app = App(self.conn)
        self.app.catalog.add_product("TEE", "T-shirt", 2500, stock=3)
        self.conn.execute(
            "INSERT INTO coupons (code, kind, value, max_uses) VALUES ('ONCE', 'fixed', 100, 1)"
        )

    def test_cancel_before_payment_puts_the_units_back(self):
        order = self.app.orders.create("sam", [("TEE", 3)], coupon_code="ONCE")
        self.assertEqual(order["status"], "pending")
        self.assertEqual(self.app.catalog.get_product("TEE").stock, 0)
        cancelled = self.app.orders.cancel(order["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.app.catalog.get_product("TEE").stock, 3)
        uses = self.conn.execute("SELECT uses FROM coupons WHERE code = 'ONCE'").fetchone()["uses"]
        self.assertEqual(uses, 0)
        again = self.app.orders.create("sam", [("TEE", 3)], coupon_code="ONCE")
        self.assertEqual(again["status"], "pending")
