-- The same extract with a classic bug, kept for the reconciliation demo: joining the daily mart to leads at the same
-- grain repeats every day's revenue once per lead (join fan-out) and drops days with no leads.
SELECT m.channel, SUM(m.order_revenue) AS revenue, SUM(m.orders) AS orders
FROM mart_channel_daily m
JOIN fact_leads l ON l.created_date = m.date AND l.channel = m.channel
GROUP BY m.channel
ORDER BY m.channel;
