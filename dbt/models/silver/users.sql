-- ---------------------------------------------------------------------------
-- users: one row per product user
-- Fixes: UPPERCASE emails -> lower case; missing job title -> 'Unknown';
-- text dates -> DATE; account routed through account_id_map.
-- ---------------------------------------------------------------------------

select
    u.user_id,
    m.account_id,
    lower(trim(u.email))                                  as email,
    trim(u.first_name)                                    as first_name,
    trim(u.last_name)                                     as last_name,
    coalesce(nullif(trim(u.job_title), ''), 'Unknown')    as job_title,
    lower(trim(u.status))                                 as status,
    cast(u.created_at as date)                            as created_at,
    cast(u.deactivated_at as date)                        as deactivated_at,
    u._source_file,
    u._loaded_at

from {{ source('bronze', 'app_users') }} u
left join {{ ref('account_id_map') }} m
       on u.account_id = m.crm_account_id
