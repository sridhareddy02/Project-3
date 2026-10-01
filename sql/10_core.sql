-- Core layer: dimensions and clean facts built from the standardised staging tables.
-- Placeholders {{start}}, {{end}} and {{extract_date}} are replaced by the pipeline.
-- Staging tables: stg_ads, stg_web, stg_leads, stg_orders (loaded by Python, ISO dates as text).

DROP TABLE IF EXISTS dim_channel;
CREATE TABLE dim_channel (
    channel  TEXT PRIMARY KEY,
    label    TEXT NOT NULL,
    is_paid  INTEGER NOT NULL
);
INSERT INTO dim_channel VALUES
    ('paid_search',    'Paid search',    1),
    ('paid_social',    'Paid social',    1),
    ('email',          'Email',          0),
    ('organic_search', 'Organic search', 0),
    ('direct',         'Direct',         0);

DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date AS
WITH RECURSIVE d(date) AS (
    SELECT '{{start}}'
    UNION ALL
    SELECT date(date, '+1 day') FROM d WHERE date < '{{end}}'
)
SELECT date,
       CAST(strftime('%w', date) AS INTEGER) AS weekday,   -- 0 = Sunday
       strftime('%Y-%W', date)               AS year_week,
       strftime('%Y-%m', date)               AS year_month
FROM d;

-- Advertising spend by day, channel and campaign. A missing campaign name is kept and labelled, never dropped.
DROP TABLE IF EXISTS fact_ad_spend;
CREATE TABLE fact_ad_spend AS
SELECT date,
       channel,
       COALESCE(campaign, '(missing)') AS campaign,
       SUM(spend)                      AS spend,
       SUM(impressions)                AS impressions,
       SUM(clicks)                     AS clicks,
       SUM(platform_conversions)       AS platform_conversions
FROM stg_ads
WHERE date IS NOT NULL
GROUP BY date, channel, COALESCE(campaign, '(missing)');

-- Web analytics by day and channel. Sources the taxonomy does not know are quarantined, not silently merged.
DROP TABLE IF EXISTS fact_web_daily;
CREATE TABLE fact_web_daily AS
SELECT date, channel,
       SUM(sessions)     AS sessions,
       SUM(transactions) AS transactions,
       SUM(revenue)      AS revenue
FROM stg_web
WHERE channel <> 'unmapped' AND date IS NOT NULL
GROUP BY date, channel;

DROP TABLE IF EXISTS quarantine_web;
CREATE TABLE quarantine_web AS
SELECT date, source_medium, sessions, transactions, revenue, 'unmapped channel' AS reason
FROM stg_web
WHERE channel = 'unmapped';

-- Leads: exact duplicates collapse via DISTINCT, then one lead per email (the earliest). Leads without an email
-- cannot be matched, so each is kept as its own record.
DROP TABLE IF EXISTS fact_leads;
CREATE TABLE fact_leads AS
SELECT lead_id, created_at, created_date, email, channel, status, owner
FROM (
    SELECT l.*,
           ROW_NUMBER() OVER (PARTITION BY COALESCE(email, lead_id) ORDER BY created_at, lead_id) AS rn
    FROM (SELECT DISTINCT lead_id, created_at, created_date, email, channel, status, owner FROM stg_leads) l
)
WHERE rn = 1;

-- Orders: only valid orders reach the fact table. Invalid ones go to quarantine with a reason.
DROP TABLE IF EXISTS fact_orders;
CREATE TABLE fact_orders AS
SELECT order_id, order_date, customer_email, channel, revenue
FROM stg_orders
WHERE revenue > 0 AND order_date <= '{{extract_date}}' AND channel <> 'unmapped';

DROP TABLE IF EXISTS quarantine_orders;
CREATE TABLE quarantine_orders AS
SELECT order_id, order_date, channel, revenue,
       CASE WHEN revenue IS NULL OR revenue <= 0 THEN 'non-positive revenue'
            WHEN order_date > '{{extract_date}}'   THEN 'order date in the future'
            ELSE 'unmapped channel' END AS reason
FROM stg_orders
WHERE NOT (revenue > 0 AND order_date <= '{{extract_date}}' AND channel <> 'unmapped');
