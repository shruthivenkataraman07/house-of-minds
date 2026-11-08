# Data quality summary

Dataset Dashboard Royale — The Gilded Ace v0.9.0-draft, source commit `5f9274bdc3efa6614e6c081becaeadda34c57a32`, fingerprint `4792a8a179571d7b`.

## Acquisition

- Tables catalogued: 31; verified against official SHA-256: 31
- Missing required: none; missing optional: none

## Tables

| table | rows | cols | grain | duplicate keys | date coverage |
|---|---|---|---|---|---|
| prepared_daily_view | 56,110 | 44 | machine x gaming date | 0 | gaming_date: 2025-01-01..2025-06-30 |
| player_period | 148,893 | 23 | tracked player x month | 0 |  |
| property_day | 181 | 24 | gaming date | 0 | gaming_date: 2025-01-01..2025-06-30 |
| calendar_day | 181 | 10 | gaming date | 0 | gaming_date: 2025-01-01..2025-06-30 |
| floor_locations | 378 | 10 | zone, bank, slot, outlet or entrance | 0 |  |
| floor_walkways | 10 | 7 | walkway between zones | 0 | closed_from_utc: 2025-03-03..2025-03-03; closed_to_utc: 2025-04-07..2025-04-07 |
| machines | 310 | 6 | machine | 0 | install_date: 2016-01-02..2025-05-13; retire_date: 2025-02-25..2025-05-13 |
| game_math | 10 | 11 | game configuration | 0 |  |
| placements | 314 | 6 | machine x location/config interval | 0 | effective_from_utc: 2025-01-01..2025-06-10; effective_to_utc: 2025-02-04..2025-06-10 |
| machine_day | 56,110 | 20 | machine x gaming date | 0 | gaming_date: 2025-01-01..2025-06-30 |
| operations | 1,226 | 10 | repair, move, install or retirement ticket | 0 | opened_at_utc: 2025-01-01..2025-07-01; available_at_utc: 2025-01-01..2025-07-01 |
| cost_rules | 9 | 10 | supplied cost rule | 0 |  |
| action_catalog | 13 | 10 | action the budget can buy | 0 |  |
| players | 113,890 | 7 | loyalty account | 0 | enrolled_at_utc: 2020-11-24..2025-07-01 |
| sessions | 776,297 | 20 | carded session segment | 0 | gaming_date: 2025-01-01..2025-06-30 |
| trips | 351,729 | 8 | observed property visit | 0 | first_observed_at_utc: 2025-01-01..2025-07-01 |
| loyalty_ledger | 782,773 | 13 | points award or redemption | 0 | event_at_utc: 2025-01-01..2025-07-01 |
| fnb_transactions | 227,833 | 14 | POS ticket | 0 | event_at_utc: 2025-01-01..2025-07-01 |
| zone_traffic_hourly | 30,401 | 10 | sensor x hour | 0 | hour_start_utc: 2025-01-01..2025-07-01 |
| events | 8 | 9 | event | 0 | start_date: 2025-01-07..2025-06-09; end_date: 2025-01-10..2025-06-15 |
| weather_daily | 181 | 23 | calendar day | 0 | source_date: 2025-01-01..2025-06-30 |
| city_visitation_monthly | 6 | 15 | month | 0 |  |
| benchmark_public | 700 | 16 | Missouri casino x slot category x month | 0 |  |
| benchmark_property_monthly | 78 | 14 | Missouri casino x month | 0 |  |
| benchmark_state_monthly | 6 | 10 | month | 0 |  |
| visitor_profile_summary | 74 | 16 | survey metric | 0 |  |
| visitor_profile_segments | 1,406 | 16 | metric x segment | 0 |  |
| machine_hour | 1,321,908 | 17 | machine x hour | 0 | gaming_date: 2025-01-01..2025-06-30 |
| security_incidents | 3,865 | 11 | reported incident | 0 | occurred_at_utc: 2025-01-01..2025-07-01 |
| shift_roster | 10,317 | 9 | staff assignment | 0 | gaming_date: 2025-01-01..2025-06-30 |
| visitor_profile_monthly | 42 | 8 | fictional survey metric x month | 0 |  |

## Findings by class

### Confirmed Error (0)

### Potential Anomaly (1)
- M-1158 payout frequency far above game math (analytical findings, section 2): the records are internally consistent, so this is a business anomaly to inspect, not a data error.

### Unverified Assumption (4)
- `benchmark_public.slot_units`: 11 nulls (1.5714%) with no documented reason; treat as unknown, not zero
- `benchmark_public.handle_usd`: 8 nulls (1.1429%) with no documented reason; treat as unknown, not zero
- `benchmark_public.actual_payout_ratio`: 17 nulls (2.4286%) with no documented reason; treat as unknown, not zero
- `benchmark_public.derived_hold_ratio`: 8 nulls (1.1429%) with no documented reason; treat as unknown, not zero

### Expected Behavior (56)
- `prepared_daily_view.federal_holiday`: 54560 nulls: Not a holiday.
- `prepared_daily_view.events_active`: 45880 nulls: No event that day.
- `prepared_daily_view.zone_id`: 1018 nulls: Null on the 1,018 documented off-floor machine-days.
- `prepared_daily_view.zone_name`: 1018 nulls: Null on the 1,018 documented off-floor machine-days.
- `prepared_daily_view.bank_id`: 1018 nulls: Null on the 1,018 documented off-floor machine-days.
- `prepared_daily_view.location_id`: 1018 nulls: Null on documented off-floor machine-days (not installed / retired).
- `prepared_daily_view.availability_ratio`: 1018 nulls: Null on off-floor machine-days.
- `prepared_daily_view.occupancy_ratio`: 1018 nulls: Null when no available hours.
- `prepared_daily_view.house_win_usd`: 7117 negative values: machines can lose money on a day (documented).
- `prepared_daily_view.observed_hold`: 1035 nulls: Undefined when coin-in is zero.
- `prepared_daily_view.theo_hold`: 1035 nulls: Undefined when coin-in is zero.
- `prepared_daily_view.luck_residual_usd`: 21916 negative values: machines can lose money on a day (documented).
- `prepared_daily_view.carded_share`: 1035 nulls: Undefined when coin-in is zero.
- `prepared_daily_view.zone_entries_observed`: 1018 nulls: Null on the 1,018 documented off-floor machine-days.
- `prepared_daily_view.zone_counter_coverage_hours`: 1018 nulls: Null on the 1,018 documented off-floor machine-days.
- `prepared_daily_view.lag_coin_in_7d_mean_usd`: 310 nulls: No prior gaming days for the first window day of each machine (310 machines).
- `prepared_daily_view.lag_downtime_7d_hours`: 310 nulls: No prior gaming days for the first window day of each machine (310 machines).
- `prepared_daily_view.lag_house_win_28d_usd`: 310 nulls: No prior gaming days for the first window day of each machine (310 machines).
- `player_period.age_band`: 17413 nulls: Documented as missing for some players.
- `player_period.luck_residual_usd`: 93162 negative values: machines can lose money on a day (documented).
- `property_day.events_active`: 148 nulls: No event that day.
- `calendar_day.federal_holiday`: 176 nulls: Not a holiday.
- `floor_locations.parent_location_id`: 7 nulls: Hierarchy: column applies only to some node types (zone/bank/slot/outlet/entrance).
- `floor_locations.bank_id`: 13 nulls: Hierarchy: column applies only to some node types (zone/bank/slot/outlet/entrance).
- `floor_locations.outlet_id`: 375 nulls: Hierarchy: column applies only to some node types (zone/bank/slot/outlet/entrance).
- `floor_locations.name`: 365 nulls: Hierarchy: column applies only to some node types (zone/bank/slot/outlet/entrance).
- `floor_locations.capacity`: 10 nulls: Hierarchy: column applies only to some node types (zone/bank/slot/outlet/entrance).
- `floor_walkways.closed_from_utc`: 9 nulls: Walkway never closed.
- `floor_walkways.closed_to_utc`: 9 nulls: Walkway never closed.
- `floor_walkways.closure_reason`: 9 nulls: Walkway never closed.
- `machines.retire_date`: 308 nulls: Machine still on the floor.
- `placements.effective_to_utc`: 308 nulls: Placement still open.
- `machine_day.location_id`: 1018 nulls: Null on documented off-floor machine-days (not installed / retired).
- `machine_day.house_win_cents`: 7117 negative values: machines can lose money on a day (documented).
- `cost_rules.entity_id`: 2 nulls: Rule applies to all entities.
- `cost_rules.effective_to`: 9 nulls: Open-ended rule.
- `action_catalog.incompatibility_group`: 7 nulls: Action has no conflict group.
- `players.age_band`: 13463 nulls: Documented as missing for some players.
- `loyalty_ledger.benefit_id`: 723412 nulls: Award rows have no redeemed benefit.
- `loyalty_ledger.redeemed_pos_id`: 723412 nulls: Award rows have no POS ticket.

## Referential integrity

| child | parent | checked | orphans | status |
|---|---|---|---|---|
| machine_day.machine_id | machines.machine_id | 56,110 | 0 | pass |
| machine_day.config_id | game_math.config_id | 56,110 | 0 | pass |
| machine_day.location_id | floor_locations.location_id | 55,092 | 0 | pass |
| machine_day.gaming_date | calendar_day.gaming_date | 56,110 | 0 | pass |
| prepared_daily_view.machine_id | machines.machine_id | 56,110 | 0 | pass |
| placements.machine_id | machines.machine_id | 314 | 0 | pass |
| placements.location_id | floor_locations.location_id | 314 | 0 | pass |
| placements.config_id | game_math.config_id | 314 | 0 | pass |
| operations.machine_id | machines.machine_id | 1,226 | 0 | pass |
| operations.location_id | floor_locations.location_id | 1,226 | 0 | pass |
| sessions.machine_id | machines.machine_id | 776,297 | 0 | pass |
| sessions.player_id | players.player_id | 776,297 | 0 | pass |
| sessions.observed_visit_id | trips.observed_visit_id | 776,297 | 0 | pass |
| trips.player_id | players.player_id | 351,729 | 0 | pass |
| loyalty_ledger.player_id | players.player_id | 782,773 | 0 | pass |
| loyalty_ledger.redeemed_pos_id | fnb_transactions.transaction_id | 59,361 | 0 | pass |
| loyalty_ledger.source_segment_id | sessions.session_segment_id | 723,412 | 0 | pass |
| fnb_transactions.player_id | players.player_id | 150,899 | 0 | pass |
| fnb_transactions.comp_id | loyalty_ledger.loyalty_event_id | 59,361 | 0 | pass |
| player_period.player_id | players.player_id | 148,893 | 0 | pass |
| zone_traffic_hourly.zone_id | floor_locations.location_id | 30,401 | 0 | pass |

## Join cardinality risks

| join | left rows | joined rows | fan-out | safe |
|---|---|---|---|---|
| machine_day x placements on machine_id only (ignoring interval) | 56,110 | 56,834 | 1.013 | False |
| active machine_day x placements on [effective_from, effective_to) interval | 55,092 | 55,092 | 1.0 | True |
| sessions x fnb_transactions on player_id (two fact tables) | 776,297 | 9,842,971 | 12.679 | False |

## Financial reconciliation

| test | description | status | tolerance | evidence |
|---|---|---|---|---|
| R01 | House win equals coin-in minus payout (integer cents) | **pass** | exact (0 cents) | `EV-EE9AA60F1EA9` |
| R02 | Prepared view dollars equal source cents / 100 | **pass** | <= $0.005 (half a cent rounding) | `EV-C2CFB61227F3` |
| R03 | property_day equals the sum of machine_day by gaming date | **pass** | <= $0.01 per day; exact machine counts | `EV-E19B0DBB42B5` |
| R04 | Availability within scheduled time within gaming day | **pass** | exact | `EV-0F24E145C2E2` |
| R05 | Active flag agrees with placements and install/retire dates | **pass** | exact | `EV-B7A651F70B6A` |
| R06 | Placement intervals are consistent and join 1:1 | **pass** | exact | `EV-C3D6B6912DCB` |
| R07 | Money totals survive the location join (no duplication) | **pass** | exact | `EV-2717136A34C6` |
| R08 | Theo equals coin-in x (1 - configured RTP) | **pass** | <= 0.0001 cents | `EV-D8FA0EB03BC9` |
| R09 | Carded play is a strict subset and reconciles across machine meters, sessions and player_period | **pass** | exact cents; <= $0.01 for player_period total | `EV-3123B1AC8417` |
| R10 | Comp cost counted once: ledger cost == linked POS cogs, and is contained in POS cogs | **pass** | exact cents per redemption; <= $0.01 per day | `EV-8F25EE4BAF3C` |
| R11 | Supplied machine costs recompute from cost_rules | **pass** | <= $0.01 per machine-day | `EV-88F23EF2648B` |
| R12 | Meter downtime reconciles to operations tickets | **pass** | <= 1% pass, <= 10% warning | `EV-0AA1543DE3EB` |
| R13 | Gaming days run 06:00-06:00 local and are contiguous | **pass** | exact | `EV-9538BCED1591` |
| R14 | Player-period accounting identities (player sign) | **pass** | <= $0.005 | `EV-B8DF60B3EF78` |

Full inputs and calculated values: `reports/reconciliation.json`.
