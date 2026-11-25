-- ============================================================
-- First look at the bronze layer
-- Run:  python scripts/run_sql.py sql/01_first_look_bronze.sql
--
-- Each query below answers one question. Read the question,
-- guess the answer, then check what the database says.
-- ============================================================


-- show: 1. What tables are in my database, and how big are they?
SELECT schema_name, table_name, estimated_size AS approx_rows, column_count
FROM duckdb_tables()
ORDER BY schema_name, table_name;


-- show: 2. What did the last load runs do? (the audit log)
SELECT load_run_id, table_name, row_count, seconds
FROM bronze._load_audit
ORDER BY loaded_at DESC, table_name
LIMIT 8;


-- show: 3. What does a raw account row look like? (note the _metadata columns at the end)
SELECT *
FROM bronze.crm_accounts
LIMIT 5;


-- show: 4. How many accounts per region? (spot the messy spellings, including 'NA')
SELECT region, count(*) AS accounts
FROM bronze.crm_accounts
GROUP BY region
ORDER BY accounts DESC;


-- show: 5. Every column is text in bronze. Proof: the data types of the invoices table
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'bronze' AND table_name = 'billing_invoices';


-- show: 6. The billing migration: invoice ID and date formats before vs after April 2025
-- Notice example_date for the new system shows 01/01/2026, not April 2025:
-- the dates are TEXT, so min() sorts them alphabetically, not by date.
-- That's exactly why silver must convert them to real DATE values.
SELECT
    CASE WHEN invoice_id LIKE 'INV-%' THEN 'old system' ELSE 'new system' END AS billing_system,
    count(*)            AS invoices,
    min(invoice_id)     AS example_id,
    min(invoice_date)   AS example_date,
    min(amount)         AS example_amount
FROM bronze.billing_invoices
GROUP BY billing_system;


-- show: 7. Schema drift: how many event rows have a platform value, by arrival file?
SELECT _source_file,
       count(*)          AS events,
       count(platform)   AS events_with_platform
FROM bronze.app_usage_events
WHERE _source_file BETWEEN 'product_app/usage_events/usage_events_2025_07.csv'
                       AND 'product_app/usage_events/usage_events_2025_10.csv'
GROUP BY _source_file
ORDER BY _source_file;


-- show: 8. Duplicate events: event_ids that appear more than once
SELECT count(*) AS duplicated_event_ids
FROM (
    SELECT event_id
    FROM bronze.app_usage_events
    GROUP BY event_id
    HAVING count(*) > 1
);
