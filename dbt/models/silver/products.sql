-- products: the six products, with typed prices and launch dates

select
    product_id,
    trim(product_name)                                    as product_name,
    cast(list_price_usd_per_seat as decimal(18, 2))       as list_price_usd_per_seat,
    cast(launch_date as date)                             as launch_date,
    _source_file,
    _loaded_at
from {{ source('bronze', 'billing_products') }}
