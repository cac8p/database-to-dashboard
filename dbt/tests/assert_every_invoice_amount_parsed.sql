-- A "singular" test: a query that should return ZERO rows.
-- Any row it returns is a failure.
--
-- Rule: every raw invoice amount must survive the text-to-number cleanup.
-- If the billing system ever sends a format we don't handle (a new currency
-- symbol, say), the cleaned amount comes back NULL and this test catches it.

select
    r.invoice_id,
    r.amount as raw_amount
from {{ source('bronze', 'billing_invoices') }} r
where r.amount is not null
  and try_cast(regexp_replace(r.amount, '[$£€,]', '', 'g') as decimal(18, 2)) is null
