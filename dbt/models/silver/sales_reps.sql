-- sales_reps: reps, their team and region, with a typed hire date

select
    rep_id,
    trim(rep_name)                                        as rep_name,
    trim(team)                                            as team,
    trim(region)                                          as region,
    cast(hire_date as date)                               as hire_date,
    _source_file,
    _loaded_at
from {{ source('bronze', 'crm_sales_reps') }}
