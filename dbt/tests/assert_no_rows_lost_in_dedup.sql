-- Rule: deduplicating events may only remove TRUE duplicates.
-- Distinct event_ids in bronze must equal rows in silver.

with b as (select count(distinct event_id) as n from {{ source('bronze', 'app_usage_events') }}),
     s as (select count(*) as n from {{ ref('usage_events') }})
select b.n as bronze_distinct_events, s.n as silver_events
from b, s
where b.n <> s.n
