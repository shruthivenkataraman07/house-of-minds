"""Financial and operational reconciliation checks.

Each check recomputes a documented relationship from source tables and reports the
difference. Nothing is adjusted to force agreement; failures are reported with causes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

from analytics.metrics import gaming_day_join
from analytics.sql_dialect import dialect_of, local_hhmm, seconds_between
from backend.repositories.base import AnalyticsRepository

Status = Literal["pass", "fail", "warning"]


class ReconciliationResult(BaseModel):
    test_id: str
    description: str
    input_data: list[str]
    calculated_result: dict[str, Any]
    expected_relationship: str
    tolerance: str
    status: Status
    explanation: str


Check = Callable[[AnalyticsRepository], ReconciliationResult]
CHECKS: list[Check] = []


def check(fn: Check) -> Check:
    CHECKS.append(fn)
    return fn


def _row(repo: AnalyticsRepository, sql: str) -> dict[str, Any]:
    df = repo.query_df(sql)
    return {k: _clean(v) for k, v in df.iloc[0].to_dict().items()}


def _clean(v: Any) -> Any:
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float):
        return round(v, 6)
    return v if isinstance(v, (int, str, bool)) or v is None else float(v)


@check
def r01_house_win_identity(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        SELECT count(*) rows_checked,
               count(*) FILTER (WHERE house_win_cents <> coin_in_cents - payout_cents) violations,
               sum(house_win_cents) / 100.0 house_win_usd,
               (sum(coin_in_cents) - sum(payout_cents)) / 100.0 coin_in_minus_payout_usd,
               count(*) FILTER (WHERE house_win_cents < 0) negative_days
        FROM machine_day""")
    ok = r["violations"] == 0
    return ReconciliationResult(
        test_id="R01", description="House win equals coin-in minus payout (integer cents)",
        input_data=["machine_day"], calculated_result=r,
        expected_relationship="house_win_cents == coin_in_cents - payout_cents, every row",
        tolerance="exact (0 cents)", status="pass" if ok else "fail",
        explanation=f"{r['negative_days']} machine-days have negative house win; these are "
                    "valid outcomes and are kept.")


@check
def r02_money_units(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        SELECT count(*) rows_checked,
          max(abs(p.coin_in_usd - m.coin_in_cents / 100.0)) max_coin_in_diff_usd,
          max(abs(p.payout_usd - m.payout_cents / 100.0)) max_payout_diff_usd,
          max(abs(p.house_win_usd - m.house_win_cents / 100.0)) max_house_win_diff_usd,
          max(abs(p.theo_usd - m.theo_cents / 100.0)) max_theo_diff_usd,
          max(abs(p.carded_coin_in_usd - m.carded_coin_in_cents / 100.0)) max_carded_diff_usd,
          max(abs(p.available_hours - m.available_seconds / 3600.0)) max_avail_hours_diff
        FROM prepared_daily_view p JOIN machine_day m USING (machine_id, gaming_date)""")
    worst = max(v for k, v in r.items() if k.startswith("max_"))
    ok = worst <= 0.005
    return ReconciliationResult(
        test_id="R02", description="Prepared view dollars equal source cents / 100",
        input_data=["prepared_daily_view", "machine_day"], calculated_result=r,
        expected_relationship="usd == cents / 100 and hours == seconds / 3600, row by row",
        tolerance="<= $0.005 (half a cent rounding)", status="pass" if ok else "fail",
        explanation="Confirms one conversion factor and no unit drift between layers.")


@check
def r03_property_rollup(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        WITH src AS (
          SELECT gaming_date, sum(coin_in_cents) / 100.0 ci, sum(payout_cents) / 100.0 po,
                 sum(house_win_cents) / 100.0 hw, sum(theo_cents)::DOUBLE / 100.0 th,
                 sum(available_seconds) / 3600.0 ah,
                 count(*) FILTER (WHERE active) am
          FROM machine_day GROUP BY 1)
        SELECT count(*) days_compared,
          max(abs(s.ci - p.coin_in_usd)) max_coin_in_diff,
          max(abs(s.po - p.payout_usd)) max_payout_diff,
          max(abs(s.hw - p.house_win_usd)) max_house_win_diff,
          max(abs(s.th - p.theo_usd)) max_theo_diff,
          max(abs(s.ah - p.available_machine_hours)) max_avail_hours_diff,
          count(*) FILTER (WHERE s.am <> p.active_machines) active_count_mismatches,
          sum(p.coin_in_usd) property_coin_in_usd, sum(s.ci) source_coin_in_usd
        FROM src s FULL JOIN property_day p USING (gaming_date)""")
    ok = (max(r["max_coin_in_diff"], r["max_payout_diff"], r["max_house_win_diff"],
              r["max_theo_diff"]) <= 0.01 and r["max_avail_hours_diff"] <= 1e-6
          and r["active_count_mismatches"] == 0 and r["days_compared"] == 181)
    return ReconciliationResult(
        test_id="R03", description="property_day equals the sum of machine_day by gaming date",
        input_data=["property_day", "machine_day"], calculated_result=r,
        expected_relationship="daily property totals == sum over machines (source cents)",
        tolerance="<= $0.01 per day; exact machine counts", status="pass" if ok else "fail",
        explanation="Validates the prepared property view against the source meters rather "
                    "than against the other prepared view.")


@check
def r04_availability_bounds(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        SELECT count(*) FILTER (WHERE m.active) active_rows,
          count(*) FILTER (WHERE m.available_seconds > m.scheduled_seconds) avail_gt_sched,
          count(*) FILTER (WHERE m.occupied_seconds > m.available_seconds) occ_gt_avail,
          count(*) FILTER (WHERE m.scheduled_seconds > c.scheduled_seconds) sched_gt_day,
          count(*) FILTER (WHERE m.active AND m.scheduled_seconds < c.scheduled_seconds)
            partial_days,
          count(*) FILTER (WHERE NOT m.active AND (m.scheduled_seconds > 0 OR m.paid_spins > 0))
            inactive_with_activity,
          sum(m.scheduled_seconds - m.available_seconds) / 3600.0 total_downtime_hours,
          sum(m.available_seconds)::DOUBLE / sum(m.scheduled_seconds) floor_availability
        FROM machine_day m JOIN calendar_day c USING (gaming_date)""")
    hard = r["avail_gt_sched"] + r["sched_gt_day"] + r["inactive_with_activity"]
    status: Status = "fail" if hard else ("warning" if r["occ_gt_avail"] else "pass")
    return ReconciliationResult(
        test_id="R04", description="Availability within scheduled time within gaming day",
        input_data=["machine_day", "calendar_day"], calculated_result=r,
        expected_relationship="occupied <= available <= scheduled <= calendar day length; "
                              "inactive rows carry no time or play",
        tolerance="exact", status=status,
        explanation=f"{r['partial_days']} active machine-days are shorter than the gaming day "
                    "(install or retirement mid-day); exposure uses scheduled_seconds, not 24 h.")


@check
def r05_active_dates(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        WITH placed AS (
          SELECT m.machine_id, m.gaming_date, count(p.placement_id) > 0 placed
          FROM machine_day m JOIN calendar_day c USING (gaming_date)
          LEFT JOIN placements p ON p.machine_id = m.machine_id
           AND p.effective_from_utc < c.gaming_day_end_utc
           AND (p.effective_to_utc IS NULL OR p.effective_to_utc > c.gaming_day_start_utc)
          GROUP BY 1, 2),
        cover AS (
          SELECT m.machine_id, m.gaming_date, m.active, pl.placed,
                 mc.install_date, mc.retire_date
          FROM machine_day m JOIN placed pl USING (machine_id, gaming_date)
          JOIN machines mc USING (machine_id))
        SELECT count(*) rows_checked,
          count(*) FILTER (WHERE active <> placed) active_vs_placement_mismatch,
          count(*) FILTER (WHERE active AND gaming_date < install_date) active_before_install,
          count(*) FILTER (WHERE active AND retire_date IS NOT NULL AND gaming_date > retire_date)
            active_after_retire,
          count(*) FILTER (WHERE NOT active) off_floor_rows
        FROM cover""")
    bad = r["active_vs_placement_mismatch"] + r["active_before_install"] + \
        r["active_after_retire"]
    return ReconciliationResult(
        test_id="R05", description="Active flag agrees with placements and install/retire dates",
        input_data=["machine_day", "placements", "machines", "calendar_day"],
        calculated_result=r,
        expected_relationship="active <=> a placement interval overlaps the gaming day; "
                              "never active before install or after retirement",
        tolerance="exact", status="pass" if bad == 0 else "fail",
        explanation=f"{r['off_floor_rows']} off-floor rows are excluded from all metrics "
                    "(documented: 1,018).")


@check
def r06_placement_history(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        WITH p AS (SELECT *, coalesce(effective_to_utc, TIMESTAMP '9999-12-31') eto
                   FROM placements),
        machine_overlap AS (
          SELECT count(*) n FROM p a JOIN p b ON a.machine_id = b.machine_id
           AND a.placement_id < b.placement_id
           AND a.effective_from_utc < b.eto AND b.effective_from_utc < a.eto),
        slot_overlap AS (
          SELECT count(*) n FROM p a JOIN p b ON a.location_id = b.location_id
           AND a.placement_id < b.placement_id
           AND a.effective_from_utc < b.eto AND b.effective_from_utc < a.eto),
        loc_match AS (
          SELECT count(*) n, count(*) FILTER (WHERE m.location_id <> p.location_id
                                              OR m.config_id <> p.config_id) mismatched
          FROM machine_day m JOIN calendar_day c USING (gaming_date)
          JOIN placements p ON p.machine_id = m.machine_id
           AND c.gaming_day_start_utc >= p.effective_from_utc
           AND (p.effective_to_utc IS NULL OR c.gaming_day_start_utc < p.effective_to_utc)
          WHERE m.active),
        boundary AS (
          SELECT count(*) FILTER (WHERE c.gaming_date IS NULL
                     AND p.effective_from_utc >= (SELECT min(gaming_day_start_utc)
                                                  FROM calendar_day)) off_boundary
          FROM placements p LEFT JOIN calendar_day c
            ON c.gaming_day_start_utc = p.effective_from_utc)
        SELECT (SELECT count(*) FROM placements) placements,
               (SELECT n FROM machine_overlap) machine_overlaps,
               (SELECT n FROM slot_overlap) slot_overlaps,
               (SELECT n FROM loc_match) interval_joined_rows,
               (SELECT mismatched FROM loc_match) location_or_config_mismatches,
               (SELECT count(*) FROM machine_day WHERE active) active_rows,
               (SELECT off_boundary FROM boundary) starts_not_on_gaming_day_boundary""")
    bad = (r["machine_overlaps"] + r["slot_overlaps"] + r["location_or_config_mismatches"]
           + r["starts_not_on_gaming_day_boundary"])
    fanout = r["interval_joined_rows"] != r["active_rows"]
    return ReconciliationResult(
        test_id="R06", description="Placement intervals are consistent and join 1:1",
        input_data=["placements", "machine_day", "calendar_day"], calculated_result=r,
        expected_relationship="no overlapping intervals per machine or per slot; interval "
                              "join reproduces machine_day location/config with no fan-out",
        tolerance="exact", status="pass" if bad == 0 and not fanout else "fail",
        explanation="Interval join [effective_from_utc, effective_to_utc) is the only "
                    "valid way to attach location history.")


@check
def r07_join_duplication(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        WITH joined AS (
          SELECT m.coin_in_cents FROM machine_day m JOIN calendar_day c USING (gaming_date)
          JOIN placements p ON p.machine_id = m.machine_id
           AND c.gaming_day_start_utc >= p.effective_from_utc
           AND (p.effective_to_utc IS NULL OR c.gaming_day_start_utc < p.effective_to_utc)
          JOIN floor_locations f ON f.location_id = p.location_id
          WHERE m.active),
        naive AS (SELECT m.coin_in_cents FROM machine_day m JOIN placements p USING (machine_id))
        SELECT (SELECT sum(coin_in_cents) FROM machine_day) / 100.0 source_coin_in_usd,
               (SELECT sum(coin_in_cents) FROM joined) / 100.0 interval_join_coin_in_usd,
               (SELECT sum(coin_in_cents) FROM naive) / 100.0 naive_join_coin_in_usd""")
    r["naive_join_overstatement_usd"] = round(
        r["naive_join_coin_in_usd"] - r["source_coin_in_usd"], 2)
    ok = abs(r["interval_join_coin_in_usd"] - r["source_coin_in_usd"]) < 0.005
    return ReconciliationResult(
        test_id="R07", description="Money totals survive the location join (no duplication)",
        input_data=["machine_day", "placements", "floor_locations", "calendar_day"],
        calculated_result=r,
        expected_relationship="coin-in after interval join == source coin-in",
        tolerance="exact", status="pass" if ok else "fail",
        explanation=f"A naive machine_id join would overstate coin-in by "
                    f"${r['naive_join_overstatement_usd']:,.2f}; the pipeline uses the "
                    "interval join only.")


@check
def r08_theo(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        SELECT count(*) rows_checked,
          max(abs(m.theo_cents - m.coin_in_cents * (1 - g.configured_rtp))) max_abs_diff_cents,
          sum(m.theo_cents)::DOUBLE / 100 theo_usd,
          sum(m.coin_in_cents * (1 - g.configured_rtp))::DOUBLE / 100 recomputed_theo_usd,
          sum(m.house_win_cents) / 100.0 house_win_usd,
          (sum(m.house_win_cents) - sum(m.theo_cents))::DOUBLE / 100 luck_residual_usd
        FROM machine_day m JOIN game_math g USING (config_id) WHERE m.active""")
    ok = r["max_abs_diff_cents"] <= 1e-4
    return ReconciliationResult(
        test_id="R08", description="Theo equals coin-in x (1 - configured RTP)",
        input_data=["machine_day", "game_math"], calculated_result=r,
        expected_relationship="theo_cents == coin_in_cents x (1 - configured_rtp) per "
                              "machine-day; luck residual == house win - theo",
        tolerance="<= 0.0001 cents", status="pass" if ok else "fail",
        explanation="Theo is a deterministic function of wagers, so it is a luck-free "
                    "demand measure. Realized win differs from theo by the luck residual.")


@check
def r09_carded_boundary(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        WITH s AS (SELECT machine_id, gaming_date, sum(coin_in_cents) ci,
                          sum(payout_cents) po, sum(theo_cents) th
                   FROM sessions GROUP BY 1, 2),
        cmp AS (SELECT m.carded_coin_in_cents mc, coalesce(s.ci, 0) sc,
                       m.carded_payout_cents mp, coalesce(s.po, 0) sp,
                       m.coin_in_cents total
                FROM machine_day m LEFT JOIN s USING (machine_id, gaming_date))
        SELECT count(*) FILTER (WHERE mc > total) carded_exceeds_total,
          count(*) FILTER (WHERE mc <> sc OR mp <> sp) machine_vs_session_mismatch,
          sum(mc) / 100.0 machine_day_carded_coin_in_usd,
          sum(sc) / 100.0 sessions_coin_in_usd,
          (SELECT sum(tracked_coin_in_usd) FROM player_period)::DOUBLE
            player_period_coin_in_usd,
          sum(total) / 100.0 all_play_coin_in_usd,
          sum(mc)::DOUBLE / sum(total) carded_share
        FROM cmp""")
    pp_diff = abs(r["player_period_coin_in_usd"] - r["sessions_coin_in_usd"])
    r["player_period_vs_sessions_diff_usd"] = round(pp_diff, 2)
    ok = (r["carded_exceeds_total"] == 0 and r["machine_vs_session_mismatch"] == 0
          and pp_diff < 0.01)
    return ReconciliationResult(
        test_id="R09", description="Carded play is a strict subset and reconciles across "
                                   "machine meters, sessions and player_period",
        input_data=["machine_day", "sessions", "player_period"], calculated_result=r,
        expected_relationship="carded <= all play per machine-day; sessions == machine_day "
                              "carded columns; player_period total == sessions total",
        tolerance="exact cents; <= $0.01 for player_period total",
        status="pass" if ok else "fail",
        explanation=f"Carded play is {r['carded_share']:.1%} of all coin-in, so guest-level "
                    "results describe tracked play only and are never scaled to all play.")


@check
def r10_comp_accounting(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, f"""
        WITH redeem AS (SELECT l.loyalty_event_id, l.economic_cost_cents, l.face_value_cents,
                               f.cogs_cents, f.face_value_cents f_face, f.cash_receipt_cents
                        FROM loyalty_ledger l
                        LEFT JOIN fnb_transactions f ON f.transaction_id = l.redeemed_pos_id
                        WHERE l.event_type = 'redeem'),
        pos_daily AS (SELECT cal.gaming_date,
                             sum(f.cogs_cents) FILTER (WHERE f.comp_id IS NOT NULL) comp_cogs,
                             sum(f.cogs_cents) cogs, sum(f.cash_receipt_cents) cash
                      FROM fnb_transactions f {gaming_day_join('f.event_at_utc')}
                      GROUP BY 1)
        SELECT (SELECT count(*) FROM redeem) redemptions,
          (SELECT count(*) FROM redeem WHERE cogs_cents IS NULL) redemptions_without_pos,
          (SELECT count(*) FROM redeem WHERE economic_cost_cents <> cogs_cents)
            cost_vs_cogs_mismatch,
          (SELECT count(*) FROM redeem WHERE cash_receipt_cents <> 0) comps_with_cash,
          (SELECT sum(economic_cost_cents) FROM redeem) / 100.0 ledger_comp_cost_usd,
          (SELECT sum(comp_cogs) FROM pos_daily) / 100.0 pos_comp_cogs_usd,
          (SELECT sum(comp_cost_usd) FROM property_day)::DOUBLE property_comp_cost_usd,
          (SELECT sum(comp_face_value_usd) FROM property_day)::DOUBLE property_comp_face_usd,
          (SELECT max(abs(p.comp_cost_usd - d.comp_cogs / 100.0)) FROM property_day p
             JOIN pos_daily d USING (gaming_date))::DOUBLE max_daily_comp_diff_usd,
          (SELECT max(abs(p.pos_cogs_usd - d.cogs / 100.0)) FROM property_day p
             JOIN pos_daily d USING (gaming_date))::DOUBLE max_daily_cogs_diff_usd,
          (SELECT count(*) FROM property_day WHERE comp_cost_usd > pos_cogs_usd)
            days_comp_exceeds_cogs,
          (SELECT sum(comp_cost_usd) FROM player_period)::DOUBLE player_period_comp_cost_usd,
          (SELECT count(*) FROM player_period WHERE comp_cost_usd > linked_pos_cogs_usd)
            players_comp_exceeds_cogs""")
    ok = (r["redemptions_without_pos"] == 0 and r["cost_vs_cogs_mismatch"] == 0
          and r["comps_with_cash"] == 0 and r["max_daily_comp_diff_usd"] <= 0.01
          and r["max_daily_cogs_diff_usd"] <= 0.01 and r["days_comp_exceeds_cogs"] == 0
          and r["players_comp_exceeds_cogs"] == 0
          and abs(r["ledger_comp_cost_usd"] - r["pos_comp_cogs_usd"]) < 0.01)
    return ReconciliationResult(
        test_id="R10", description="Comp cost counted once: ledger cost == linked POS cogs, "
                                   "and is contained in POS cogs",
        input_data=["loyalty_ledger", "fnb_transactions", "property_day", "player_period"],
        calculated_result=r,
        expected_relationship="economic_cost_cents == linked cogs_cents; comp cost is a "
                              "subset of pos_cogs; comp face value is not revenue",
        tolerance="exact cents per redemption; <= $0.01 per day",
        status="pass" if ok else "fail",
        explanation="Contribution must subtract POS cogs once (comps included) and must not "
                    "subtract comp cost a second time. Face value "
                    f"(${r['property_comp_face_usd']:,.0f}) is menu price, not cost.")


@check
def r11_supplied_costs(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, f"""
        WITH rules AS (SELECT * FROM cost_rules),
        rate AS (SELECT
          (SELECT rate::DOUBLE FROM rules WHERE cost_rule_id = 'CR-LEASE-FIXED') lease_fixed,
          (SELECT rate::DOUBLE FROM rules WHERE cost_rule_id = 'CR-LEASE-SHARE') lease_share,
          (SELECT rate::DOUBLE FROM rules WHERE cost_rule_id = 'CR-POWER') power),
        svc AS (SELECT entity_id manufacturer, rate::DOUBLE svc_rate FROM rules
                WHERE entity_type = 'manufacturer'),
        repair AS (SELECT o.machine_id, cal.gaming_date, sum(o.direct_cost_cents) c
                   FROM operations o {gaming_day_join('o.opened_at_utc')}
                   WHERE o.event_type = 'fault_repair' GROUP BY 1, 2),
        calc AS (
          SELECT p.machine_id, p.gaming_date, p.lease_cost_usd, p.service_cost_usd,
            p.power_cost_usd, p.repair_cost_usd,
            CASE mc.lease_class
              WHEN 'leased_fixed' THEN (SELECT lease_fixed FROM rate)
              WHEN 'leased_revenue_share' THEN
                (SELECT lease_share FROM rate) * greatest(m.house_win_cents, 0)
              ELSE 0 END / 100.0 lease_calc,
            coalesce(svc.svc_rate, 0) / 100.0 service_calc,
            (SELECT power FROM rate) / 100.0 power_calc,
            coalesce(rp.c, 0) / 100.0 repair_calc
          FROM prepared_daily_view p
          JOIN machine_day m USING (machine_id, gaming_date)
          JOIN machines mc USING (machine_id)
          LEFT JOIN repair rp USING (machine_id, gaming_date)
          LEFT JOIN svc ON svc.manufacturer = mc.manufacturer
          WHERE p.active)
        SELECT count(*) active_rows,
          max(abs(lease_cost_usd - lease_calc)) max_lease_diff,
          max(abs(service_cost_usd - service_calc)) max_service_diff,
          max(abs(power_cost_usd - power_calc)) max_power_diff,
          max(abs(repair_cost_usd - repair_calc)) max_repair_diff,
          count(*) FILTER (WHERE abs(lease_cost_usd - lease_calc) > 0.01) lease_rows_off,
          count(*) FILTER (WHERE abs(repair_cost_usd - repair_calc) > 0.01) repair_rows_off,
          sum(lease_cost_usd + service_cost_usd + power_cost_usd + repair_cost_usd)::DOUBLE
            supplied_costs_usd,
          sum(lease_calc + service_calc + power_calc + repair_calc) recomputed_costs_usd
        FROM calc""")
    worst = max(r["max_lease_diff"], r["max_service_diff"], r["max_power_diff"],
                r["max_repair_diff"])
    status: Status = "pass" if worst <= 0.01 else (
        "warning" if abs(r["supplied_costs_usd"] - r["recomputed_costs_usd"]) < 1 else "fail")
    return ReconciliationResult(
        test_id="R11", description="Supplied machine costs recompute from cost_rules",
        input_data=["prepared_daily_view", "machine_day", "machines", "cost_rules",
                    "operations"],
        calculated_result=r,
        expected_relationship="lease/service/power per active machine-day and repair "
                              "direct cost by gaming date of fault opening match the "
                              "prepared view",
        tolerance="<= $0.01 per machine-day", status=status,
        explanation="Confirms the cost_rules interpretation used for contribution and "
                    "for pricing downtime. Revenue-share lease = 20% of positive daily win.")


@check
def r12_operations_vs_downtime(repo: AnalyticsRepository) -> ReconciliationResult:
    d = dialect_of(repo)
    r = _row(repo, f"""
        WITH w AS (SELECT min(gaming_day_start_utc) s, max(gaming_day_end_utc) e
                   FROM calendar_day),
        ops AS (SELECT event_type,
                  sum({seconds_between('greatest(opened_at_utc, w.s)',
                                       'least(available_at_utc, w.e)', d)}) / 3600.0 hrs
                FROM operations, w
                WHERE available_at_utc > w.s AND opened_at_utc < w.e
                GROUP BY 1)
        SELECT (SELECT sum(scheduled_seconds - available_seconds) FROM machine_day) / 3600.0
                 meter_downtime_hours,
               (SELECT sum(hrs) FROM ops) ticket_outage_hours,
               (SELECT hrs FROM ops WHERE event_type = 'fault_repair') fault_repair_hours,
               (SELECT hrs FROM ops WHERE event_type = 'install') install_hours,
               (SELECT hrs FROM ops WHERE event_type = 'move') move_hours,
               (SELECT hrs FROM ops WHERE event_type = 'scheduled_maintenance')
                 maintenance_hours""")
    gap = r["meter_downtime_hours"] - r["ticket_outage_hours"]
    r["unexplained_hours"] = round(gap, 3)
    rel = abs(gap) / r["meter_downtime_hours"] if r["meter_downtime_hours"] else 0
    status: Status = "pass" if rel <= 0.01 else ("warning" if rel <= 0.10 else "fail")
    return ReconciliationResult(
        test_id="R12", description="Meter downtime reconciles to operations tickets",
        input_data=["machine_day", "operations", "calendar_day"], calculated_result=r,
        expected_relationship="scheduled - available (meters) ~= sum of ticket outage "
                              "intervals clipped to the window",
        tolerance="<= 1% pass, <= 10% warning", status=status,
        explanation="Ticket intervals can include time when a machine was not scheduled "
                    "(e.g. install before first gaming day) or overlap; differences are "
                    "reported, not forced.")


@check
def r13_gaming_day_dst(repo: AnalyticsRepository) -> ReconciliationResult:
    d = dialect_of(repo)
    r = _row(repo, f"""
        WITH c AS (SELECT *, lead(gaming_day_start_utc) OVER (ORDER BY gaming_date) nxt
                   FROM calendar_day)
        SELECT count(*) n_days,
          count(*) FILTER (WHERE {seconds_between('gaming_day_start_utc',
                                                  'gaming_day_end_utc', d)}
                           <> scheduled_seconds) length_mismatch,
          count(*) FILTER (WHERE scheduled_seconds <> 86400) non_24h_days,
          min(scheduled_seconds) min_seconds,
          (SELECT scheduled_seconds FROM calendar_day WHERE gaming_date = DATE '2025-03-08')
            dst_day_seconds,
          count(*) FILTER (WHERE nxt IS NOT NULL AND nxt <> gaming_day_end_utc)
            gaps_between_days,
          count(*) FILTER (WHERE {local_hhmm('gaming_day_start_utc', d)} <> '06:00')
            non_6am_starts
        FROM c""")
    ok = (r["n_days"] == 181 and r["length_mismatch"] == 0 and r["dst_day_seconds"] == 82800
          and r["non_24h_days"] == 1 and r["non_6am_starts"] == 0
          and r["gaps_between_days"] == 0)
    return ReconciliationResult(
        test_id="R13", description="Gaming days run 06:00-06:00 local and are contiguous",
        input_data=["calendar_day"], calculated_result=r,
        expected_relationship="181 contiguous days; each starts at 06:00 Los Angeles time; "
                              "only 2025-03-08 is 23 h",
        tolerance="exact", status="pass" if ok else "fail",
        explanation="Exposure uses scheduled_seconds, so the DST day is not overstated by 1 h.")


@check
def r14_player_accounting(repo: AnalyticsRepository) -> ReconciliationResult:
    r = _row(repo, """
        SELECT count(*) rows_checked,
          count(*) FILTER (WHERE abs(tracked_net_usd - (tracked_payout_usd - tracked_coin_in_usd))
                           > 0.005) net_violations,
          count(*) FILTER (WHERE abs(luck_residual_usd - (tracked_net_usd + theo_usd)) > 0.005)
            residual_violations,
          count(*) FILTER (WHERE abs(tracked_contribution_usd - (-tracked_net_usd
                    + linked_pos_cash_usd - linked_pos_cogs_usd)) > 0.005) contribution_violations,
          sum(tracked_net_usd)::DOUBLE tracked_player_net_usd,
          sum(theo_usd)::DOUBLE tracked_theo_usd
        FROM player_period""")
    ok = r["net_violations"] + r["residual_violations"] + r["contribution_violations"] == 0
    return ReconciliationResult(
        test_id="R14", description="Player-period accounting identities (player sign)",
        input_data=["player_period"], calculated_result=r,
        expected_relationship="net = payout - coin-in; residual = net + theo; contribution = "
                              "-net + POS cash - POS cogs (comp cost not subtracted again)",
        tolerance="<= $0.005", status="pass" if ok else "fail",
        explanation="Player tables use the opposite sign to machine tables.")


def run_all(repo: AnalyticsRepository) -> list[ReconciliationResult]:
    results = []
    for fn in CHECKS:
        try:
            results.append(fn(repo))
        except Exception as exc:  # report, never hide
            results.append(ReconciliationResult(
                test_id=fn.__name__.split("_")[0].upper(), description=fn.__name__,
                input_data=[], calculated_result={"error": repr(exc)},
                expected_relationship="check executes", tolerance="n/a", status="fail",
                explanation="The check itself raised an error; investigate before trusting "
                            "related metrics."))
    return results
