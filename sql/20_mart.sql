-- Mart layer: one row per day and channel with every source side by side.
-- The grid is date x channel, so a day missing from a source shows up as NULL instead of vanishing.

DROP TABLE IF EXISTS mart_channel_daily;
CREATE TABLE mart_channel_daily AS
WITH grid AS (
    SELECT d.date, d.weekday, d.year_week, d.year_month, c.channel, c.is_paid
    FROM dim_date d CROSS JOIN dim_channel c
),
ads AS (
    SELECT date, channel, SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks
    FROM fact_ad_spend GROUP BY date, channel
),
ord AS (
    SELECT order_date AS date, channel, COUNT(*) AS orders, SUM(revenue) AS order_revenue
    FROM fact_orders GROUP BY order_date, channel
),
ld AS (
    SELECT created_date AS date, channel, COUNT(*) AS leads
    FROM fact_leads GROUP BY created_date, channel
)
SELECT g.date, g.weekday, g.year_week, g.year_month, g.channel, g.is_paid,
       a.spend, a.impressions, a.clicks,
       w.sessions, w.transactions, w.revenue AS web_revenue,
       o.orders, o.order_revenue,
       l.leads
FROM grid g
LEFT JOIN ads a ON a.date = g.date AND a.channel = g.channel
LEFT JOIN fact_web_daily w ON w.date = g.date AND w.channel = g.channel
LEFT JOIN ord o ON o.date = g.date AND o.channel = g.channel
LEFT JOIN ld  l ON l.date = g.date AND l.channel = g.channel;
