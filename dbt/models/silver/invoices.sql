-- ---------------------------------------------------------------------------
-- invoices: clean invoices and credit notes, in local currency AND USD
--
-- Fixes for the April 2025 billing-system migration:
--   * two date formats   2024-03-15  and  03/15/2025  -> one DATE type
--   * two amount formats 7584.00     and  "$13,200.00" / "£4,100.00" / "€2,950.00"
--                                                        -> one DECIMAL number
--   * exact duplicate rows re-sent by the new system  -> keep one per invoice_id
-- Adds:
--   * billing_system (legacy / new), document_type (invoice / credit_note)
--   * amount_usd using that month's exchange rate
-- ---------------------------------------------------------------------------

with raw as (

    select * from {{ source('bronze', 'billing_invoices') }}

),

parsed as (

    select
        invoice_id,
        subscription_id,
        account_id                                                  as crm_account_id,

        -- try the old format first, then the new one; whichever works wins
        coalesce(try_strptime(invoice_date, '%Y-%m-%d'),
                 try_strptime(invoice_date, '%m/%d/%Y'))::date      as invoice_date,
        coalesce(try_strptime(due_date, '%Y-%m-%d'),
                 try_strptime(due_date, '%m/%d/%Y'))::date          as due_date,
        coalesce(try_strptime(paid_date, '%Y-%m-%d'),
                 try_strptime(paid_date, '%m/%d/%Y'))::date         as paid_date,

        -- strip currency symbols and thousands separators, then make it a number
        try_cast(regexp_replace(amount, '[$£€,]', '', 'g') as decimal(18, 2))
                                                                    as amount_local,

        upper(trim(currency))                                       as currency,
        lower(trim(status))                                         as status,
        case when invoice_id like 'INV-%' then 'legacy' else 'new' end
                                                                    as billing_system,
        _source_file,
        _loaded_at

    from raw

),

deduped as (

    select *
    from parsed
    qualify row_number() over (partition by invoice_id order by _loaded_at) = 1

),

fx as (

    select * from {{ ref('fx_rates_monthly') }}

),

fx_bounds as (

    select min(rate_month) as first_month, max(rate_month) as last_month from fx

)

select
    i.invoice_id,
    i.subscription_id,
    m.account_id,
    i.invoice_date,
    i.due_date,
    i.paid_date,
    case when i.status = 'credit_note' then 'credit_note' else 'invoice' end
                                                                    as document_type,
    i.status,
    i.amount_local,
    i.currency,
    cast(round(i.amount_local / fx.units_per_usd, 2) as decimal(18, 2))
                                                                    as amount_usd,
    i.billing_system,
    i._source_file,
    i._loaded_at

from deduped i
left join {{ ref('account_id_map') }} m
       on i.crm_account_id = m.crm_account_id
cross join fx_bounds b
left join fx
       on fx.currency   = i.currency
      -- invoices outside the FX history use the nearest month available
      and fx.rate_month = least(greatest(date_trunc('month', i.invoice_date), b.first_month), b.last_month)
