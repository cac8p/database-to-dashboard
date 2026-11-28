-- ---------------------------------------------------------------------------
-- usage_events: one clean row per real product event
--
-- Fixes:
--   * duplicate events (client retries)  -> keep one row per event_id
--   * casing bug Jun-Jul 2024            -> LOGIN / Login / "report download" -> login / report_download
--   * two timestamp formats              -> one TIMESTAMP
--   * schema drift                       -> platform is NULL before Sep 2025 (it wasn't logged yet)
-- Adds:
--   * is_service_account_event: API calls with no person attached
--   * ingestion_lag_hours / is_late_arriving: events that showed up days late
-- Always analyze on event_at (when it happened), never on the file it arrived in.
-- ---------------------------------------------------------------------------

with raw as (

    select * from {{ source('bronze', 'app_usage_events') }}

),

parsed as (

    select
        event_id,
        account_id                                                  as crm_account_id,
        user_id,
        product_id,
        replace(lower(trim(event_type)), ' ', '_')                  as event_type,
        coalesce(try_strptime(event_timestamp, '%Y-%m-%dT%H:%M:%SZ'),
                 try_strptime(event_timestamp, '%Y-%m-%d %H:%M:%S')) as event_at,
        try_strptime(ingested_at, '%Y-%m-%d %H:%M:%S')              as ingested_at,
        lower(trim(platform))                                       as platform,
        _source_file,
        _loaded_at
    from raw

),

deduped as (

    select *
    from parsed
    qualify row_number() over (partition by event_id order by ingested_at, _source_file) = 1

)

select
    e.event_id,
    m.account_id,
    e.user_id,
    e.product_id,
    e.event_type,
    e.event_at,
    cast(e.event_at as date)                                        as event_date,
    e.ingested_at,
    round(date_diff('minute', e.event_at, e.ingested_at) / 60.0, 1) as ingestion_lag_hours,
    date_diff('minute', e.event_at, e.ingested_at) > 24 * 60        as is_late_arriving,
    e.user_id is null                                               as is_service_account_event,
    e.platform,
    e._source_file,
    e._loaded_at

from deduped e
left join {{ ref('account_id_map') }} m
       on e.crm_account_id = m.crm_account_id
