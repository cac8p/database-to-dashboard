-- ---------------------------------------------------------------------------
-- subscriptions: one row per product per contract term, typed and in USD
--
-- The billing system is fairly clean, so this is mostly about TYPES:
-- text -> dates, integers and decimals. Also adds the contract value in USD
-- (using the exchange rate for the month the contract started) and routes
-- the account through account_id_map.
-- ---------------------------------------------------------------------------

with raw as (

    select * from {{ source('bronze', 'billing_subscriptions') }}

),

fx as (

    select * from {{ ref('fx_rates_monthly') }}

),

fx_bounds as (

    select min(rate_month) as first_month, max(rate_month) as last_month from fx

),

typed as (

    select
        subscription_id,
        account_id                                       as crm_account_id,
        product_id,
        cast(contract_start_date as date)                as contract_start_date,
        cast(contract_end_date as date)                  as contract_end_date,
        cast(term_months as integer)                     as term_months,
        cast(seats as integer)                           as seats,
        cast(discount_pct as decimal(5, 2))              as discount_pct,
        cast(annual_contract_value as decimal(18, 2))    as acv_local,
        upper(trim(currency))                            as currency,
        lower(trim(status))                              as status,
        previous_subscription_id,
        signed_by_rep_id,
        booking_type,
        _source_file,
        _loaded_at
    from raw

)

select
    s.subscription_id,
    m.account_id,
    s.product_id,
    s.contract_start_date,
    s.contract_end_date,
    s.term_months,
    s.seats,
    s.discount_pct,
    s.acv_local,
    s.currency,
    -- contracts before the FX history starts use the earliest rate available
    cast(round(s.acv_local / fx.units_per_usd, 2) as decimal(18, 2)) as acv_usd,
    s.status,
    s.booking_type,
    s.previous_subscription_id,
    s.signed_by_rep_id,
    s._source_file,
    s._loaded_at

from typed s
left join {{ ref('account_id_map') }} m
       on s.crm_account_id = m.crm_account_id
cross join fx_bounds b
left join fx
       on fx.currency   = s.currency
      and fx.rate_month = least(greatest(date_trunc('month', s.contract_start_date), b.first_month), b.last_month)
