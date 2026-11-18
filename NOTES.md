# NOTES

Fill in every field below before you submit. We read this file first: a submission with an empty field is not graded.
Write in your own words. If you did not fix something, set Status to `not fixed` and say what you found and tried; that still counts.
Status is one of: `fixed`, `partly fixed`, `not fixed`. Commits: the short hashes of the commits for this item, or `none`.

## 1. Report

> Finance says that on some days the revenue in the daily report is higher than what the payment provider paid out, and a few orders show more money received than their total.

**Status:** fixed

**What I saw:** A mug order totals 1200 cents. Delivering `payment.succeeded` with event id `evt_1` and `amount_cents` 1200 marks it paid. Delivering that same event again leaves the order paid, but `paid_cents` becomes 2400 and the payments table has two rows for `evt_1`. `daily_sales` for that day then reports `revenue_cents` 2400 for one order. The provider only paid 1200. Two different event ids that add up to the total (500 then 700) still reach exactly 1200, so partial payments were not the problem.

**Root cause:** The provider retries a webhook until it gets a 2xx, and `handle_event` inserted a payments row on every delivery. `event_id` was not unique. `paid_cents` and the daily report both sum those rows, so a retry was counted as new money and an order could show more received than its total.

**Fix and why:** Record an event id once. `handle_event` now looks up `event_id` inside a transaction and skips the insert when that id is already stored. `payments.event_id` has a unique index, and a concurrent insert that loses the race rolls back and returns the order status instead of adding a second row. A different event id is still a different payment, so real partial payments keep summing.

**How I verified it:** `tests/test_payments.py` failed on the original code with `paid_cents` 2400 != 1200. After the fix the retry stays at 1200, one row, and daily revenue 1200. The partial-payment test stays at 1200 and status `paid`. Full suite passes. A cancelled order still returns 409 and writes no payment row.

**Commits:** d90cb2a

## 2. Report

> Products show as sold out, or nearly, while the shelf is full. Staff say it gets worse on days when many customers abandon checkout.

**Status:** fixed

**What I saw:** Three tees in stock. Creating an order for all three, still `pending`, drops stock to 0. Cancelling that order before any payment leaves stock at 0 and status `cancelled`. The next customer cannot buy a tee. The coupon use does come back. Cancelling an order that was already paid did put the units back; the existing test covered only that path.

**Root cause:** Stock is taken in `Orders.create`, before payment. `cancel` promised to put the stock back, but it only called `release` when status was already `paid`. An abandoned checkout is cancelled while it is still `pending`, so the units stayed reserved in the catalog even though they never left the shelf. Each abandoned checkout made it worse.

**Fix and why:** Any cancel of an order that has not shipped now returns every line's quantity. Pending and paid both reserved the same way, at create, so both need the same release. Shipped orders still cannot be cancelled. I did not stop reserving stock at create: the existing order test expects the hold, and it is what stops two checkouts from taking the last unit. An order that is left pending on purpose still holds its units until someone cancels it. A timeout for that hold would be a separate product decision and I did not build one.

**How I verified it:** `tests/test_cancel.py` failed on the original code with stock 0 != 3 after cancelling the pending order. After the fix the stock is 3, the one-use coupon is usable again, and a new order for those three tees succeeds. `test_cancel_paid_order_restocks` still passes. Full suite passes.

**Commits:** 43803f7

## 3. Report

> Customers in taxed regions who used a coupon say the tax on their receipt is too high. Receipts without a coupon are right.

**Status:** fixed

**What I saw:** One mug is 1200 cents. In CA (725 basis points, 7.25%) with no coupon, tax is 87 and the total is 1287. That matches 7.25% of 1200. The same mug with coupon `TEN` (10%) gets a 120 cent discount, but tax stays 87 and the total is 1167. Tax on the discounted 1080 cents is 78, not 87.

**Root cause:** `price_order` computed tax from the full subtotal, then subtracted the coupon. The discount never reduced the amount that was taxed. With no coupon the discount is 0, so those receipts were already right.

**Fix and why:** Apply the coupon first, then tax `subtotal - discount`. The total is still subtotal minus discount plus that tax. A 100% discount taxes 0. Regions without a coupon are unchanged.

**How I verified it:** `tests/test_pricing.py` failed on the original code with tax 87 != 78 for the CA order with `TEN`. After the fix that order is discount 120, tax 78, total 1158. The no-coupon assertion stays at tax 87 and total 1287, and the original CA test (two mugs and a tee, no coupon, tax 355) still passes. Full suite passes.

**Commits:** a086a22

## 4. Report

> Our shop in India (UTC+5:30) says sales taken in the morning do not appear in that day's report and turn up under the day before.

**Status:** fixed

**What I saw:** India is 330 minutes ahead of UTC. A payment at 15 Jun 2025 08:00 IST is 15 Jun 2025 02:30 UTC. With `utc_offset_minutes=330`, that payment was absent from 15 Jun (revenue 0) and present on 14 Jun (revenue 1200). The window for 15 Jun was `2025-06-15T05:30:00Z` to `2025-06-16T05:30:00Z`. Local morning is before 05:30 UTC, so it fell in the previous window. A sale at 23:00 IST the same day (17:30 UTC) did show up on the 15th, which is why it looked like "mornings only". Offset 0 was already midnight to midnight UTC.

**Root cause:** `day_bounds_utc` added the offset to UTC midnight. For a shop east of UTC, local midnight is earlier than UTC midnight, so the offset has to be subtracted. Adding it pushed the whole shop day forward. The 30 minutes matter: India is not a whole number of hours, and the parameter is already in minutes.

**Fix and why:** Start the shop day at UTC midnight minus `utc_offset_minutes`. For 15 Jun in India that is `2025-06-14T18:30:00Z` through `2025-06-15T18:30:00Z`. Offset 0 is unchanged. A negative offset, a shop west of UTC, moves the start later, which is the same formula.

**How I verified it:** `tests/test_reports.py` failed on the original code: 15 Jun revenue was 0, not 2400. The test pays three times: 08:00 IST on the 15th (02:30Z), 00:15 IST on the 15th (14 Jun 18:45Z, inside the half hour a 5-hour shift would miss), and 23:30 IST on the 14th (14 Jun 18:00Z), which must stay on the 14th. After the fix, 15 Jun is 2400 cents and 2 orders, 14 Jun is 1200 cents and 1 order. The original UTC daily-sales test still passes. Full suite passes. Printed bounds after the fix: 15 Jun is `2025-06-14T18:30:00Z` to `2025-06-15T18:30:00Z`.

**Commits:** a73a953

## 5. Report

> Ever since we started running two server workers, we have sold more units of an item than we had, and its stock went negative.

**Status:** fixed

**What I saw:** Two connections, two `Catalog` objects, one mug in stock. The second worker loads the mug and caches stock 1. The first worker reserves that mug. The database stock is 0. The second worker's `reserve` still succeeds, and stock becomes -1. The same thing happened with two threads that each cached the row and then reserved: both returned ok, stock -1. One worker alone still refuses to sell a tee when stock is short; that path was already tested.

**Root cause:** `reserve` decided from the per-process cache (`get_product`) and then ran `stock = stock - qty` with no condition. Each worker has its own cache, and the check and the update were not one statement. Both workers could see the last unit and both updates applied.

**Fix and why:** The update is now `SET stock = stock - ? WHERE sku = ? AND stock >= ?`. If no row changes, it is either an unknown sku or `OutOfStock` using the stock actually in the database. The cache is dropped either way, and it is no longer the thing that allows the sale. SQLite applies that update as one write, so the second worker's statement sees the first worker's commit and changes nothing.

**How I verified it:** `tests/test_stock.py` opens two connections to one database file, warms the second cache, reserves from the first, and expects the second reserve to raise. On the original code `OutOfStock` was not raised. After the fix it is raised and the row stays at 0. `test_out_of_stock` still passes, including the rollback that leaves stock untouched when the order cannot be created. Full suite passes.

**Commits:** 6552761

## 6. Open question

> Open question from support, no single right answer: sometimes a customer really does pay twice for one order (two separate payments, not a retry of the same one). Today the system records both and says nothing. Decide what should happen, build the smallest version of your decision, and explain what it costs in `NOTES.md`.

**My decision:** Keep both payments, leave the order `paid` so it can still ship, and say so on the order and on the webhook response with `received_cents` and `overpaid_cents`. Do not return an error for the second charge.

**Why:** The two event ids are two charges the provider has already taken. Report 1 is the retry case, same event id, and that one must not count twice. This case is different. Rejecting the second webhook with 409 does not give the money back, and the provider retries until it gets a 2xx, so the extra charge would either be retried forever or, if we dropped it, disappear from our books while the customer was still charged. Blocking shipment would punish someone who did pay for the goods. The smallest honest behaviour is to store the money and make the extra amount visible for a person to refund.

**What it costs:** The customer is charged twice until someone refunds `overpaid_cents` outside this app. There is no refund call to the provider here, so nothing moves the money back automatically. Daily revenue includes the extra payment, which matches what the provider actually paid out and is higher than the order total; the order's `overpaid_cents` is how finance tells those apart. Support has to notice the field. A shop that would rather refuse the second charge at the provider, before capture, needs a step this code does not have.

**What I built:** `Payments.balance` reports `received_cents` and `overpaid_cents` (`max(0, received - total)`). `Orders.get` adds both fields, so the order, a cancel, and a ship all show them. The payment webhook returns 200 with the same fields. A repeated event id still does not increase them. Two different ids of 1200 on a 1200 order show received 2400 and overpaid 1200, status stays `paid`, and the order can ship.

**How I verified it:** `tests/test_overpay.py` failed on the previous code with `KeyError: 'overpaid_cents'`. After the change the second webhook is 200, `overpaid_cents` is 1200, two payment rows exist, and ship returns `shipped`. A retry of the same id stays at received 1200 and overpaid 0. Full suite passes.

**Commits:** 4daa02e

## Other things I noticed

Not fixed, left on purpose after the reports:

- Cancelling a paid order returns the stock and the coupon use, but the payment rows stay. The daily report still counts that money. There is no refund, so I did not delete the payment. Same gap if a partial payment is sitting on an order that is later cancelled.
- `Catalog.get_product` still caches the whole product in that process, including stock and price. Reserve no longer trusts the cache, so two workers cannot drive stock negative, but a worker that already loaded a sku can keep showing the old stock or the old price on `GET /products` until something on that worker drops the cache. I left the read cache in place.
- A coupon's `max_uses` check and the `uses = uses + 1` update are still two steps. Two workers can both accept a one-use coupon. Same shape as the stock race. Not one of the reports.
- `handle_event` does not reject a negative `amount_cents`. A negative amount would shrink `received_cents`. The provider payload is trusted.
- An order that is never cancelled keeps the stock it reserved at create. I treated that as the hold, not as the abandon bug. The bug was cancel-before-pay failing to release. An expiry for unpaid orders is not built.
- `GET /reports/daily/<day>` reads `utc_offset_minutes` from the JSON body, which is what the README says. A client that cannot send a body on GET cannot pass the offset.

## Session logs

Cursor, this one chat. The brief's export is the chat menu, Export Chat, into `session_logs/`. That export leaves out terminal commands and file edits, so the commands and what they showed are here.

I could not press Export Chat from inside the session, and I did not write a shortened substitute over the raw export. `session_logs/` still has its README only. Drop the export in next to it before sending the zip. Until that file is there, the submission is not gradable.

Commands, in order, from `tillpoint_assignment`:

- `git status`, `git log --oneline -5`, `python3 -m unittest discover -s tests -v`. Clean tree, one commit `3b491a7`, 7 tests ok.
- A reproduction script. Webhook retry: `paid_cents` 2400, two payment rows, daily revenue 2400. Cancel of a pending 3-tee order left stock at 0. The script then raised `OutOfStock` trying to create another order.
- A second script for the rest. CA mug with `TEN`: tax 87, while tax on 1080 is 78. India offset 330: 15 Jun revenue 0, 14 Jun revenue 1200, bounds `2025-06-15T05:30:00Z` to `2025-06-16T05:30:00Z`. Two catalogs: second reserve succeeded, stock -1. Two threads: both reserved, stock -1. Two different payment ids: both responses `200 {"status": "paid"}`, `paid_cents` 2400, order dict had no received or overpaid field.
- `python3 -m unittest tests.test_payments -v` before the fix: FAIL `2400 != 1200`. After the fix, full suite 9 tests ok.
- `python3 -m unittest tests.test_cancel -v` before the fix: FAIL stock `0 != 3`. After the fix, full suite 10 tests ok.
- `python3 -m unittest tests.test_pricing -v` before the fix: FAIL tax `87 != 78`. After the fix, full suite 12 tests ok.
- `python3 -m unittest tests.test_reports -v` before the fix: FAIL 15 Jun revenue `0 != 2400`. After the fix, full suite 13 tests ok.
- `python3 -m unittest tests.test_stock -v` before the fix: FAIL `OutOfStock not raised`. After the fix, full suite 14 tests ok.
- `python3 -m unittest tests.test_overpay -v` before the change: ERROR `KeyError: 'overpaid_cents'`. After the change, full suite 15 tests ok.
- A last check: payment on a cancelled order is 409 and writes no row. Retry of a successful payment stays received 1200, overpaid 0. `day_bounds_utc('2025-06-15', 330)` is `2025-06-14T18:30:00Z` to `2025-06-15T18:30:00Z`.
