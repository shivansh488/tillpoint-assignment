"""Payment provider webhooks. The provider retries a delivery until it gets a 2xx, so events can repeat."""
import sqlite3

from . import db


class PaymentError(Exception):
    pass


class Payments:
    def __init__(self, conn):
        self.conn = conn

    def handle_event(self, event, now=None):
        """event: dict(id, type, order_id, amount_cents). Returns the order's status after the event.

        The same event id is one payment the provider is retrying. It is recorded once.
        """
        if event.get("type") != "payment.succeeded":
            return None
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            order = self.conn.execute("SELECT * FROM orders WHERE id = ?", (event["order_id"],)).fetchone()
            if order is None:
                raise PaymentError(f"payment for unknown order {event['order_id']}")
            if order["status"] == "cancelled":
                raise PaymentError(f"order {order['id']} is cancelled")
            status = order["status"]
            already = self.conn.execute(
                "SELECT 1 FROM payments WHERE event_id = ?", (event["id"],)
            ).fetchone()
            if already is None:
                self.conn.execute(
                    "INSERT INTO payments (order_id, event_id, amount_cents, received_at) VALUES (?, ?, ?, ?)",
                    (order["id"], event["id"], event["amount_cents"], db.to_iso(now or db.utcnow())),
                )
                if status == "pending" and self.paid_cents(order["id"]) >= order["total_cents"]:
                    self.conn.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (order["id"],))
                    status = "paid"
            self.conn.execute("COMMIT")
            return status
        except sqlite3.IntegrityError:
            self._rollback()
            row = self.conn.execute(
                "SELECT status FROM orders WHERE id = ?", (event["order_id"],)
            ).fetchone()
            return row["status"] if row is not None else None
        except Exception:
            self._rollback()
            raise

    def _rollback(self):
        if self.conn.in_transaction:
            self.conn.execute("ROLLBACK")

    def paid_cents(self, order_id):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS paid FROM payments WHERE order_id = ?", (order_id,)
        ).fetchone()
        return row["paid"]

    def balance(self, order_id, total_cents):
        """How much has actually arrived, and how much of it is above the order total.

        A second, different payment is kept: the provider has already taken the money,
        and it retries until it gets a 2xx, so refusing the webhook would hide the charge
        and would not give the money back. Callers can see overpaid_cents and refund it.
        """
        received = self.paid_cents(order_id)
        return {"received_cents": received, "overpaid_cents": max(0, received - total_cents)}
