# Machine comparison (first pass)

Reference machine: median theo per available hour $18.15 x median 4,330 available hours.

## Bottom-10 lists

- **raw** (`EV-C151E0401354`): M-5076, M-1158, M-1120, M-1118, M-1238, M-1181, M-1035, M-1179, M-1017, M-1265
- **exposure_adjusted** (`EV-3279F30307CD`): M-5076, M-1158, M-1120, M-1238, M-1181, M-1035, M-1179, M-1017, M-1265, M-1256
- **luck_aware** (`EV-92BEC35F7C62`): M-1120, M-5076, M-1017, M-1035, M-1265, M-1181, M-1238, M-1179, M-1048, M-1162
- **vs_same_config_peers** (`EV-2CD698F57D7F`): M-1008, M-1120, M-1244, M-1286, M-1141, M-1014, M-1045, M-1214, M-1006, M-1241

## Ranking changes (machines in any bottom-10)

| machine_id | zone_id | config_id | house_win_usd | active_days | availability_rate | luck_z | hit_rate_z_cfg | theo_per_available_hour | rank_raw | rank_exposure_adjusted | rank_luck_aware | rank_vs_peers | p_bottom_luck_aware | explanation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M-5076 | Z-B40 | G-VID95 | 3,573.25 | 49 | 0.995 | -1.85 | -0.045 | 6.39 | 1 | 1 | 2 | 23 | 1.00 | limited_exposure,unlucky_within_chance,low_demand_location,low_theo_game_config |
| M-1158 | Z-B40 | G-STD90 | 15,796.25 | 181 | 0.999 | -4.57 | 124.19 | 11.97 | 2 | 2 | 46 | 293 | 0.00 | payout_anomaly,significant_luck_shortfall,low_demand_location |
| M-1120 | Z-B40 | G-VID95 | 16,355.00 | 132 | 0.995 | -0.788 | 0.558 | 6.00 | 3 | 3 | 1 | 2 | 1.00 | limited_exposure,low_demand_location,low_theo_game_config |
| M-1118 | Z-HL | G-HL90 | 20,050.00 | 55 | 0.995 | -0.649 | 1.04 | 19.28 | 4 | 115 | 176 | 310 | 0.00 | limited_exposure |
| M-1238 | Z-B40 | G-VID95 | 24,932.75 | 181 | 0.997 | -1.81 | 0.267 | 7.65 | 5 | 4 | 7 | 303 | 1.00 | unlucky_within_chance,low_demand_location,low_theo_game_config |
| M-1181 | Z-B40 | G-HIGH92 | 26,977.00 | 181 | 0.998 | -2.41 | 2.08 | 7.50 | 6 | 5 | 6 | 54 | 1.00 | unlucky_within_chance,low_demand_location,low_theo_game_config |
| M-1035 | Z-B40 | G-VID95 | 30,303.50 | 181 | 0.999 | -0.136 | -0.753 | 7.12 | 7 | 6 | 4 | 228 | 1.00 | low_demand_location,low_theo_game_config |
| M-1179 | Z-B40 | G-HIGH92 | 30,393.75 | 181 | 0.996 | -1.46 | 1.42 | 7.81 | 8 | 7 | 8 | 133 | 1.00 | low_demand_location,low_theo_game_config |
| M-1017 | Z-B40 | G-VID95 | 31,939.50 | 181 | 0.998 | 0.578 | -0.885 | 6.82 | 9 | 8 | 3 | 107 | 1.00 | low_demand_location,low_theo_game_config |
| M-1265 | Z-B40 | G-HIGH92 | 32,071.00 | 181 | 0.998 | -0.060 | 0.070 | 7.43 | 10 | 9 | 5 | 42 | 1.00 | low_demand_location,low_theo_game_config |
| M-1256 | Z-B40 | G-STD90 | 36,176.25 | 181 | 0.998 | -1.62 | 0.376 | 11.19 | 11 | 10 | 32 | 185 | 0.00 | unlucky_within_chance,low_demand_location |
| M-1162 | Z-GAR | G-VID95 | 37,104.25 | 181 | 0.996 | 0.035 | 0.683 | 8.54 | 14 | 13 | 10 | 25 | 0.797 | low_theo_game_config |
| M-1048 | Z-B40 | G-LOW92 | 37,330.75 | 181 | 0.990 | 1.09 | -1.62 | 8.53 | 16 | 15 | 9 | 20 | 0.781 | low_demand_location,low_theo_game_config |
| M-1014 | Z-B40 | G-PEN89 | 55,730.20 | 181 | 0.994 | 0.152 | -1.31 | 12.75 | 71 | 70 | 58 | 6 | 0.00 | low_demand_location |
| M-1008 | Z-B40 | G-STD90 | 56,695.50 | 181 | 0.997 | 2.14 | -0.480 | 9.61 | 75 | 73 | 15 | 1 | 0.00 | low_demand_location |
| M-1241 | Z-BAR | G-STD90 | 63,421.25 | 181 | 0.987 | -0.511 | 1.06 | 15.86 | 108 | 106 | 117 | 10 | 0.00 | no_distinct_signal |
| M-1045 | Z-B40 | G-NEO88 | 66,463.40 | 181 | 0.999 | 1.51 | 0.803 | 12.43 | 119 | 116 | 54 | 7 | 0.00 | low_demand_location |
| M-1286 | Z-GAR | G-STD90 | 66,544.50 | 181 | 0.999 | 0.542 | -1.21 | 14.29 | 120 | 117 | 90 | 4 | 0.00 | no_distinct_signal |
| M-1006 | Z-HTL | G-CLS93 | 70,139.00 | 181 | 1.00 | -1.31 | 0.248 | 16.91 | 136 | 130 | 135 | 9 | 0.00 | no_distinct_signal |
| M-1141 | Z-HTL | G-NEO88 | 89,233.20 | 181 | 0.995 | 0.198 | -1.11 | 20.15 | 210 | 201 | 197 | 5 | 0.00 | no_distinct_signal |
| M-1214 | Z-HL | G-HL90 | 101,995.00 | 181 | 0.999 | 2.79 | -1.59 | 15.09 | 263 | 253 | 103 | 8 | 0.00 | no_distinct_signal |
| M-1244 | Z-HTL | G-JKP88 | 104,357.00 | 181 | 0.996 | 0.640 | -0.368 | 20.64 | 276 | 269 | 205 | 3 | 0.00 | no_distinct_signal |

## Raw bottom-10 shortfall decomposition (sum over 10 machines, USD)

Evidence `EV-E7D9F597BA06`

- luck: $-63,357
- exposure: $-133,046
- location: $-225,495
- game_config: $-135,324
- machine_residual: $3,545

## Zones

| zone_id | zone_name | machines | zone_theo_per_available_hour | zone_win_per_available_hour |
|---|---|---|---|---|
| Z-B40 | Back Forty | 49 | 11.71 | 11.42 |
| Z-HL | High-Limit Room | 25 | 16.64 | 17.64 |
| Z-GAR | Garage Entrance | 36 | 16.90 | 16.97 |
| Z-BAR | Bar Row | 49 | 17.76 | 17.67 |
| Z-HTL | Hotel Corridor | 37 | 18.21 | 18.35 |
| Z-PIT | Center Pit | 80 | 20.80 | 20.76 |
| Z-ENT | Main Entrance | 37 | 21.36 | 21.65 |

## Persistence test (`EV-955F2384D49D`)

```json
{
 "machines_compared": 300,
 "split": "rank on 2025-01-01..2025-03-31, evaluate on 2025-04-01..2025-06-30",
 "rankings": {
  "raw_house_win": {
   "h1_bottom10": [
    "M-1157",
    "M-1120",
    "M-1158",
    "M-1238",
    "M-1532",
    "M-1181",
    "M-1179",
    "M-1041",
    "M-1168",
    "M-1162"
   ],
   "h2_mean_win_percentile": 0.149,
   "h2_mean_theo_percentile": 0.113,
   "h2_still_bottom_quintile": 8,
   "p_value_vs_random_10": 0.0
  },
  "win_per_available_hour": {
   "h1_bottom10": [
    "M-1157",
    "M-1120",
    "M-1158",
    "M-1238",
    "M-1181",
    "M-1179",
    "M-1041",
    "M-1168",
    "M-1162",
    "M-1265"
   ],
   "h2_mean_win_percentile": 0.115,
   "h2_mean_theo_percentile": 0.079,
   "h2_still_bottom_quintile": 9,
   "p_value_vs_random_10": 0.0
  },
  "theo_per_available_hour": {
   "h1_bottom10": [
    "M-1120",
    "M-1017",
    "M-1035",
    "M-1181",
    "M-1265",
    "M-1238",
    "M-1179",
    "M-1162",
    "M-1063",
    "M-1048"
   ],
   "h2_mean_win_percentile": 0.04,
   "h2_mean_theo_percentile": 0.019,
   "h2_still_bottom_quintile": 10,
   "p_value_vs_random_10": 0.0
  }
 },
 "spearman_h1_h2_win_per_ah": 0.795,
 "spearman_h1_h2_theo_per_ah": 0.987
}
```

