-- Rule: after merging duplicates, each (domain, country) pair is one account.
-- (Domain alone is NOT unique: two different companies can share a web address.)

select domain, country, count(*) as accounts
from {{ ref('accounts') }}
group by domain, country
having count(*) > 1
