import unittest

from tillpoint import db
from tillpoint.api import App


class TaxAfterCouponTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect()
        self.app = App(self.conn)
        self.app.catalog.add_product("MUG", "Mug", 1200, stock=5)
        self.conn.execute("INSERT INTO coupons (code, kind, value) VALUES ('TEN', 'percent', 10)")

    def test_tax_is_charged_on_the_discounted_subtotal(self):
        order = self.app.orders.create("ana", [("MUG", 1)], region="CA", coupon_code="TEN")
        # 1200 - 10% = 1080 taxable. CA is 7.25% -> 78.3 cents, half-up to 78.
        self.assertEqual(order["subtotal_cents"], 1200)
        self.assertEqual(order["discount_cents"], 120)
        self.assertEqual(order["tax_cents"], 78)
        self.assertEqual(order["total_cents"], 1158)

    def test_tax_without_a_coupon_is_unchanged(self):
        order = self.app.orders.create("ana", [("MUG", 1)], region="CA")
        self.assertEqual(order["discount_cents"], 0)
        self.assertEqual(order["tax_cents"], 87)
        self.assertEqual(order["total_cents"], 1287)
