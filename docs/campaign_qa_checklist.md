# Campaign QA checklist

A reusable checklist for launching or changing a paid, email or owned-channel campaign so that measurement works from day one.

## Before launch
- [ ] Objective, primary KPI and secondary KPIs written down; success threshold agreed with the stakeholder
- [ ] Audience definition and exclusions reviewed (existing customers, internal traffic, suppression lists)
- [ ] Offer, price, dates and legal text checked against the brief
- [ ] Every link tested; destination page loads and shows the right offer
- [ ] Tracking parameters present and consistent with the naming convention (source, medium, campaign, content)
- [ ] Naming matches the channel taxonomy so reporting maps it automatically (no new `source / medium` without adding it)
- [ ] Conversion event fires once, with the right value, on a test purchase
- [ ] Send or flight schedule, time zone, daily budget and frequency caps checked
- [ ] Control group or holdout defined if the campaign will be measured for incrementality
- [ ] Dashboard, report filters and alert thresholds updated for the new campaign

## Launch day
- [ ] First hour: impressions and clicks are arriving and spend is within the expected band
- [ ] Sessions appear in web analytics with the right source and medium
- [ ] A test conversion appears in analytics and in the order system
- [ ] Unsubscribe, error and bounce rates normal (email)

## After launch (daily, then weekly)
- [ ] Data-quality gate passes; investigate any failing check before reading performance
- [ ] Spend, sessions, transactions and orders reconcile within tolerance
- [ ] Performance compared with the same weekday, not just yesterday
- [ ] Anything unexpected is explained, annotated in the report and recorded in the incident log
- [ ] At the end: results summarised against the original objective, with limitations stated
