import unittest

from tillpoint import db
from tillpoint.api import App


class SecondPaymentTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect()
        self.app = App(self.conn)
        self.app.catalog.add_product("MUG", "Mug", 1200, stock=5)

    def test_a_second_real_payment_is_recorded_and_called_out(self):
        order = self.app.orders.create("ana", [("MUG", 1)])
        first_status, first = self.app.handle("POST", "/webhooks/payments", {
            "id": "evt_a", "type": "payment.succeeded", "order_id": order["id"], "amount_cents": 1200,
        })
        self.assertEqual(first_status, 200)
        self.assertEqual(first["status"], "paid")
        self.assertEqual(first["overpaid_cents"], 0)

        # A different event id is a second charge, not a retry of evt_a.
        second_status, second = self.app.handle("POST", "/webhooks/payments", {
            "id": "evt_b", "type": "payment.succeeded", "order_id": order["id"], "amount_cents": 1200,
        })
        self.assertEqual(second_status, 200)
        self.assertEqual(second["status"], "paid")
        self.assertEqual(second["received_cents"], 2400)
        self.assertEqual(second["overpaid_cents"], 1200)

        seen = self.app.orders.get(order["id"])
        self.assertEqual(seen["status"], "paid")
        self.assertEqual(seen["received_cents"], 2400)
        self.assertEqual(seen["overpaid_cents"], 1200)
        self.assertEqual(self.app.orders.ship(order["id"])["status"], "shipped")
        rows = self.conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
        self.assertEqual(rows, 2)
