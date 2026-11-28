-- fx_rates_monthly: local currency units per 1 USD, by month
-- (synthetic for now; later this can be swapped for real FRED exchange-rate data)

select
    cast(month as date)                                   as rate_month,
    upper(trim(currency))                                 as currency,
    cast(units_per_usd as decimal(12, 6))                 as units_per_usd,
    _source_file,
    _loaded_at
from {{ source('bronze', 'ref_fx_rates_monthly') }}
