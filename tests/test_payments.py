import unittest
from datetime import datetime, timezone

from tillpoint import db, reports
from tillpoint.api import App


class WebhookRetryTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect()
        self.app = App(self.conn)
        self.app.catalog.add_product("MUG", "Mug", 1200, stock=5)

    def test_retry_of_the_same_webhook_is_not_extra_money(self):
        order = self.app.orders.create("ana", [("MUG", 1)])
        when = datetime(2025, 3, 10, 12, 0, tzinfo=timezone.utc)
        event = {
            "id": "evt_1",
            "type": "payment.succeeded",
            "order_id": order["id"],
            "amount_cents": 1200,
        }
        self.assertEqual(self.app.payments.handle_event(event, now=when), "paid")
        self.assertEqual(self.app.payments.handle_event(event, now=when), "paid")
        self.assertEqual(self.app.payments.paid_cents(order["id"]), order["total_cents"])
        rows = self.conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
        self.assertEqual(rows, 1)
        self.assertEqual(reports.daily_sales(self.conn, "2025-03-10")["revenue_cents"], 1200)

    def test_two_partial_payments_still_add_up(self):
        order = self.app.orders.create("ana", [("MUG", 1)])
        when = datetime(2025, 3, 10, 12, 0, tzinfo=timezone.utc)
        first = {"id": "evt_a", "type": "payment.succeeded", "order_id": order["id"], "amount_cents": 500}
        second = {"id": "evt_b", "type": "payment.succeeded", "order_id": order["id"], "amount_cents": 700}
        self.assertEqual(self.app.payments.handle_event(first, now=when), "pending")
        self.assertEqual(self.app.payments.handle_event(second, now=when), "paid")
        self.assertEqual(self.app.payments.paid_cents(order["id"]), 1200)
