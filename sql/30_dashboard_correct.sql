-- The revenue-by-channel extract behind the dashboard, written correctly: aggregate the mart directly.
SELECT channel, SUM(order_revenue) AS revenue, SUM(orders) AS orders
FROM mart_channel_daily
GROUP BY channel
ORDER BY channel;
