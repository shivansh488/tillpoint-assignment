import unittest
from datetime import datetime, timezone

from tillpoint import db, reports
from tillpoint.api import App


class IndiaDayBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect()
        self.app = App(self.conn)
        self.app.catalog.add_product("MUG", "Mug", 1200, stock=5)
        self.ist = 5 * 60 + 30

    def _pay(self, when, event_id):
        order = self.app.orders.create("ria", [("MUG", 1)])
        self.app.payments.handle_event(
            {
                "id": event_id,
                "type": "payment.succeeded",
                "order_id": order["id"],
                "amount_cents": order["total_cents"],
            },
            now=when,
        )

    def test_morning_sale_in_india_stays_on_that_local_day(self):
        # 15 Jun 2025 08:00 IST == 02:30 UTC. The half hour past midnight is
        # 00:15 IST == 14 Jun 18:45 UTC, which a whole-hour shift would miss.
        # 14 Jun 23:30 IST == 14 Jun 18:00 UTC and still belongs to the 14th.
        self._pay(datetime(2025, 6, 15, 2, 30, tzinfo=timezone.utc), "morning")
        self._pay(datetime(2025, 6, 14, 18, 45, tzinfo=timezone.utc), "just_after_midnight")
        self._pay(datetime(2025, 6, 14, 18, 0, tzinfo=timezone.utc), "late_on_the_14th")
        self.assertEqual(reports.daily_sales(self.conn, "2025-06-15", self.ist),
                         {"day": "2025-06-15", "revenue_cents": 2400, "orders": 2})
        self.assertEqual(reports.daily_sales(self.conn, "2025-06-14", self.ist),
                         {"day": "2025-06-14", "revenue_cents": 1200, "orders": 1})
