-- ---------------------------------------------------------------------------
-- account_id_map: fixes duplicate CRM accounts
--
-- Problem: reps sometimes created a second record for a company that already
-- existed ("ACME CORP" vs "Acme Corp Inc."). The names differ, but the
-- website is the same company, once we strip "https://", "www." and casing.
--
-- Solution: normalize the website into a bare domain, then point every CRM
-- record at the EARLIEST record with that domain AND country (the "master"
-- record).
--
-- Why country too? Matching on domain alone wrongly merged two different
-- companies that happen to share a web address (e.g. "Collin S.A.R.L." in
-- the US and "Collin SARL" in Canada). Every true duplicate shares a country,
-- so adding it removes those false positives.
-- Every other silver model uses this map, so all activity rolls up to one
-- account per real company.
-- ---------------------------------------------------------------------------

with crm as (

    select
        account_id                                            as crm_account_id,
        try_strptime(created_at, '%Y-%m-%d %H:%M:%S')         as created_at,
        -- lower-case, trim, strip "http(s)://" and "www.", drop trailing "/"
        regexp_replace(
            regexp_replace(lower(trim(website)), '^(https?://)?(www\.)?', ''),
            '/+$', ''
        )                                                     as domain,
        case
            when lower(trim(country)) in ('usa', 'us', 'u.s.', 'united states') then 'United States'
            else trim(country)
        end                                                   as country
    from {{ source('bronze', 'crm_accounts') }}

)

select
    crm_account_id,
    first_value(crm_account_id) over (
        partition by domain, country
        order by created_at, crm_account_id
    )                                                         as account_id,
    domain,
    country
from crm
