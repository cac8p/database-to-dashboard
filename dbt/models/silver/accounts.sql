-- ---------------------------------------------------------------------------
-- accounts: one clean row per real company
--
-- Fixes:
--   * duplicate CRM records  -> keep only master records (via account_id_map)
--   * region spellings       -> NA / N. America / north america / ... -> standard list
--   * country spellings      -> USA / US / U.S. -> United States
--   * missing industry/size  -> 'Unknown' (kept, never dropped)
--   * text dates             -> real TIMESTAMP
-- ---------------------------------------------------------------------------

with crm as (

    select * from {{ source('bronze', 'crm_accounts') }}

),

id_map as (

    select * from {{ ref('account_id_map') }}

),

duplicate_counts as (

    select account_id, count(*) as crm_record_count
    from id_map
    group by account_id

)

select
    m.account_id,
    trim(c.company_name)                                       as company_name,
    m.domain,

    coalesce(nullif(trim(c.industry), ''), 'Unknown')          as industry,

    case
        when lower(trim(c.region)) in ('north america', 'na', 'n. america') then 'North America'
        when lower(trim(c.region)) in ('emea', 'europe')                    then 'EMEA'
        when lower(trim(c.region)) in ('apac', 'asia pacific')              then 'APAC'
        when lower(trim(c.region)) in ('latam', 'latin america')            then 'LATAM'
        else 'Unknown'
    end                                                        as region,

    case
        when lower(trim(c.country)) in ('usa', 'us', 'u.s.', 'united states') then 'United States'
        else trim(c.country)
    end                                                        as country,

    coalesce(nullif(trim(c.employee_band), ''), 'Unknown')     as employee_band,
    try_strptime(c.created_at, '%Y-%m-%d %H:%M:%S')            as created_at,
    c.account_owner_rep_id,
    c.acquisition_channel,
    d.crm_record_count,                                        -- >1 means duplicates were merged in

    c._source_file,
    c._loaded_at

from crm c
join id_map m
  on c.account_id = m.crm_account_id
 and m.crm_account_id = m.account_id                           -- master records only
join duplicate_counts d
  on d.account_id = m.account_id
