-- Rule: exactly one exchange rate per currency per month.
-- Two rates for the same month would double-count every converted amount.

select rate_month, currency, count(*) as rates
from {{ ref('fx_rates_monthly') }}
group by rate_month, currency
having count(*) > 1
