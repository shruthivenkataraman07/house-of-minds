"""Phase 1 Step 1 pipeline: manifest -> profile -> reconcile -> analyse -> contracts -> reports.

Usage:
  uv run python scripts/run_step1.py                       # local DuckDB (Phase 1)
  uv run python scripts/run_step1.py --backend databricks  # Unity Catalog + SQL warehouse

Local mode reads only the official files and makes no network calls. Databricks mode
re-verifies the uploaded files, rebuilds bronze Delta tables, runs the same analytics on
the SQL warehouse and writes gold Delta tables. Outputs go to reports/<backend>/ for
databricks (reports/ for local) so the two runs can be compared.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    _SCRIPT = Path(__file__).resolve()
except NameError:  # Databricks serverless runs the file via exec() without __file__
    _SCRIPT = Path(sys.argv[0]).resolve()
ROOT = _SCRIPT.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from typing import Any  # noqa: E402

import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402

from analytics import contracts as C  # noqa: E402
from analytics import investigations as INV  # noqa: E402
from analytics.machine_performance import BOTTOM_N, compare_machines, persistence_test  # noqa: E402
from analytics.metrics import METRICS  # noqa: E402
from backend.schemas.contracts import CONTRACTS  # noqa: E402
from config.settings import get_settings  # noqa: E402
from evidence.recorder import EvidenceRecorder  # noqa: E402
from evidence.schema import ValidationState as VS  # noqa: E402
from models import temporal_split as TS  # noqa: E402
from optimization.action_catalog import ActionCatalog, SelectedAction, price_selection  # noqa: E402
from pipelines.ingestion.loader import data_dir, open_local_repository  # noqa: E402
from pipelines.ingestion.manifest import build_manifest  # noqa: E402
from pipelines.validation.profiling import profile_all  # noqa: E402
from pipelines.validation.reconciliation import run_all as run_reconciliation  # noqa: E402

WINDOW = ("2025-01-01", "2025-06-30")


def dump(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["duckdb", "databricks"], default=None)
    ap.add_argument("--skip-bronze", action="store_true",
                    help="databricks: reuse existing bronze tables")
    ap.add_argument("--skip-profile", action="store_true",
                    help="reuse the existing data_profile.json (profiling is descriptive)")
    ap.add_argument("--warehouse-id", help="overrides DATABRICKS_WAREHOUSE_ID")
    ap.add_argument("--catalog", help="overrides DATABRICKS_CATALOG")
    ap.add_argument("--schema", help="overrides DATABRICKS_SCHEMA")
    ap.add_argument("--output-dir", help="overrides HOM_OUTPUT_DIR (writable scratch path)")
    args = ap.parse_args(argv)
    for flag, env in [("warehouse_id", "DATABRICKS_WAREHOUSE_ID"),
                      ("catalog", "DATABRICKS_CATALOG"), ("schema", "DATABRICKS_SCHEMA"),
                      ("output_dir", "HOM_OUTPUT_DIR")]:
        if getattr(args, flag):
            os.environ[env] = getattr(args, flag)
    get_settings.cache_clear()
    t0 = time.time()
    s = get_settings()
    backend = args.backend or s.data_backend
    out_root = Path(os.environ.get("HOM_OUTPUT_DIR", str(ROOT)))
    if backend == "databricks":
        reports = out_root / s.reports_dir / "databricks"
        processed = out_root / "data" / "processed" / "databricks"
    else:
        reports = out_root / s.reports_dir
        processed = out_root / "data" / "processed"
    reports.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    print("1/8 manifest")
    repo: Any
    if backend == "databricks":
        from backend.repositories.databricks_repo import DatabricksRepository
        from pipelines.ingestion.databricks_bronze import (
            load_bronze,
            verify_volume_files,
            volume_root,
        )
        # The official manifest verified locally travels with the code.
        manifest = json.loads((ROOT / s.reports_dir / "dataset_manifest.json").read_text())
        if not s.databricks_warehouse_id:
            print("DATABRICKS_WAREHOUSE_ID is not set")
            return 1
        repo = DatabricksRepository(s.databricks_warehouse_id, s.databricks_catalog,
                                    s.databricks_schema, s.databricks_profile)
        root = volume_root(s.databricks_catalog, s.databricks_schema)
        vol = verify_volume_files(repo._ws, manifest, root)
        bad = [v["table"] for v in vol if not v["verified"]]
        dump(reports / "volume_verification.json", vol)
        if bad:
            print("Volume files do not match the official hashes:", bad)
            return 1
        if not args.skip_bronze:
            bronze = load_bronze(repo, manifest, root)
            dump(reports / "bronze_load.json", bronze)
            if any(b["status"] != "pass" for b in bronze):
                print("Bronze row counts differ from the manifest")
                return 1
    else:
        manifest = build_manifest(data_dir(s))
        dump(reports / "dataset_manifest.json", manifest)
        if manifest["missing_required"]:
            print("Missing required sources:", manifest["missing_required"])
            return 1
        repo = open_local_repository(s)
    ev = EvidenceRecorder(processed / "evidence_ledger.jsonl", manifest["fingerprint"])

    print("2/8 profile")
    if args.skip_profile and (reports / "data_profile.json").exists():
        profile = json.loads((reports / "data_profile.json").read_text())
    else:
        profile = profile_all(repo)
        dump(reports / "data_profile.json", profile)

    print("3/8 reconciliation")
    recon = run_reconciliation(repo)
    recon_ids = {}
    for r in recon:
        recon_ids[r.test_id] = ev.record(
            source_tables=r.input_data, calculation_id=f"reconciliation.{r.test_id}",
            metric=r.description, date_range=WINDOW, result=r.calculated_result, unit="mixed",
            validation_state=VS.RECONCILED if r.status == "pass" else VS.UNVERIFIED,
            claim=f"{r.expected_relationship} -> {r.status}", domain="validation",
            assumptions=[r.tolerance], limitations=[r.explanation])
    dump(reports / "reconciliation.json", [r.model_dump() for r in recon])

    print("4/8 machine comparison")
    cmp = compare_machines(repo)
    persist = persistence_test(repo)
    m = cmp.machines
    lists = {k: m.nsmallest(BOTTOM_N, col).machine_id.tolist() for k, col in {
        "raw": "house_win_usd", "exposure_adjusted": "win_per_available_hour",
        "luck_aware": "theo_per_available_hour", "vs_same_config_peers": "machine_vs_peer_index",
    }.items()}
    mc_ids = {}
    for k, ids in lists.items():
        mc_ids[k] = ev.record(
            source_tables=["machine_day", "game_math", "prepared_daily_view"],
            calculation_id=f"machine_performance.bottom10.{k}", metric=f"bottom-10 ({k})",
            filters={"active": True}, date_range=WINDOW, result=ids, unit="machine_id list",
            validation_state=VS.DESCRIPTIVE, domain="machine_performance",
            claim=f"Bottom {BOTTOM_N} machines by {k} ranking",
            limitations=["Rankings are not proof of machine quality"])
    mc_ids["persistence"] = ev.record(
        source_tables=["machine_day", "game_math"],
        calculation_id="machine_performance.persistence",
        metric="Q1 bottom-10 percentile in Q2", date_range=WINDOW, result=persist,
        unit="percentile", validation_state=VS.TESTED, domain="machine_performance",
        uncertainty={"p_values_vs_random": {k: v["p_value_vs_random_10"]
                                            for k, v in persist["rankings"].items()}},
        claim="Luck-free demand ranking persists across quarters more than win ranking")
    raw_bottom = m.nsmallest(BOTTOM_N, "house_win_usd")
    decomp_cols = ["gap_luck_usd", "gap_exposure_usd", "gap_location_usd",
                   "gap_game_config_usd", "gap_machine_residual_usd"]
    decomp = raw_bottom[decomp_cols].sum()
    mc_ids["decomposition"] = ev.record(
        source_tables=["machine_day", "game_math", "prepared_daily_view"],
        calculation_id="machine_performance.shortfall_decomposition",
        metric="raw bottom-10 shortfall vs typical machine", date_range=WINDOW,
        result={k: round(float(v), 0) for k, v in decomp.items()}, unit="USD",
        validation_state=VS.DESCRIPTIVE, domain="machine_performance",
        assumptions=[f"typical machine = median theo/ah ${cmp.reference_rate:.2f} x median "
                     f"{cmp.reference_hours:.0f} available hours"],
        claim="Exact additive split of the raw bottom-10 shortfall")

    print("5/8 investigations")
    inv = INV.run_all(repo)
    inv_sources = {
        "payout_anomaly": ["machine_day", "game_math"],
        "walkway_closure": ["floor_walkways", "calendar_day", "machine_day",
                            "prepared_daily_view", "zone_traffic_hourly"],
        "downtime_by_manufacturer": ["operations", "machine_day", "machines"],
        "comp_rate_change": ["loyalty_ledger", "calendar_day", "property_day", "machine_day"],
    }
    inv_ids = {k: ev.record(
        source_tables=inv_sources[k], calculation_id=f"investigations.{k}", metric=k,
        date_range=WINDOW, result={kk: vv for kk, vv in v.items()
                                   if kk not in ("limitations", "method")},
        unit="mixed", validation_state=VS.TESTED, domain="investigations",
        claim=v.get("observation", k), limitations=[v.get("limitations", "")])
        for k, v in inv.items()}
    dump(reports / "investigations.json", inv)

    print("6/8 contracts")
    catalog = ActionCatalog.load(repo)
    tables = {"machine_performance": C.machine_performance(cmp),
              "intervention_planning": C.intervention_planning(catalog)}
    for name, fn in C.BUILDERS.items():
        tables[name] = fn(repo)
    for spec in CONTRACTS:
        df = tables[spec.domain]
        df.to_parquet(processed / f"{spec.output_table}.parquet", index=False)
        if backend == "databricks":
            repo.write_table(spec.output_table, pa.Table.from_pandas(df, preserve_index=False))
        spec.evidence_ids.append(ev.record(
            source_tables=spec.input_datasets, calculation_id=f"contract.{spec.domain}",
            metric="contract table", date_range=WINDOW,
            result={"rows": len(df), "columns": list(df.columns)}, unit="rows",
            validation_state=VS.DESCRIPTIVE, domain=spec.domain,
            claim=f"{spec.output_table} built and schema-validated"))
    dump(reports / "data_contracts.json", [c.model_dump() for c in CONTRACTS])

    print("7/8 modeling prep + catalog")
    frame = TS.build_daily_frame(repo)
    TS.assert_no_leakage(frame, TS.ALLOWED_FEATURES)
    frame.to_parquet(processed / "modeling_daily_floor.parquet", index=False)
    split = TS.split_summary(frame)
    ev.record(source_tables=["property_day", "calendar_day", "events"],
              calculation_id="models.temporal_split", metric="split summary",
              date_range=WINDOW, result=split, unit="days", validation_state=VS.DESCRIPTIVE,
              domain="modeling", claim="Temporal split built; holdout untouched")
    example = price_selection(catalog, [SelectedAction(action_type_id="A-REPLACE-LEASE",
                                                       quantity=1)])
    catalog_summary = {aid: a.summary() for aid, a in catalog.actions.items()}
    dump(reports / "action_catalog.json", {
        "actions": catalog_summary,
        "guide_example_lease_one_unit_usd": example.total_usd,
    })

    print("8/8 reports")
    ev_path = ev.flush()
    if backend == "databricks":
        ev_rows = [json.loads(json.dumps(r.model_dump(mode="json"), default=str))
                   for r in ev.records]
        repo.write_table("evidence_ledger", pa.Table.from_pylist(
            [{**{k: (json.dumps(v, default=str) if isinstance(v, (dict, list)) else v)
                 for k, v in r.items()}} for r in ev_rows]))
        repo.write_table("reconciliation_results", pa.Table.from_pylist(
            [{**r.model_dump(), "calculated_result": json.dumps(r.calculated_result,
                                                                default=str),
              "input_data": ",".join(r.input_data)} for r in recon]))
        repo.write_table("machine_comparison", pa.Table.from_pandas(
            m.drop(columns=["install_date", "retire_date"], errors="ignore"),
            preserve_index=False))
    write_quality_md(reports, manifest, profile, recon, recon_ids)
    write_machine_md(reports, cmp, lists, persist, mc_ids, decomp)
    m.to_csv(reports / "machine_comparison.csv", index=False)
    write_findings_md(reports, cmp, lists, persist, inv, inv_ids, mc_ids, decomp, recon,
                      split, manifest)
    dump(reports / "metric_registry.json", [x.as_dict() for x in METRICS])
    if backend == "duckdb":
        write_metric_registry_md(ROOT / "docs" / "METRIC_REGISTRY.md")
    summary = {"elapsed_seconds": round(time.time() - t0, 1),
               "reconciliation": {r.test_id: r.status for r in recon},
               "evidence_records": len(ev.records), "evidence_store": str(ev_path),
               "dataset_fingerprint": manifest["fingerprint"], "backend": backend,
               "guide_example_lease_cost_usd": example.total_usd}
    dump(reports / "run_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if all(r.status != "fail" for r in recon) else 2


# ---------------------------------------------------------------- markdown writers
def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(_fmt(v) for v in r) + " |")
    return "\n".join(lines)


def _fmt(v: object) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) >= 1 or v == 0 else f"{v:.3f}"
    return str(v)


def write_metric_registry_md(path: Path) -> None:
    out = ["# Metric registry", "",
           "Generated from `analytics/metrics.py` (the single source of formulas) by "
           "`scripts/run_step1.py`. Do not edit by hand.", ""]
    for x in METRICS:
        out += [f"## {x.name} (`{x.id}`)", "", x.definition, "",
                f"- **Formula:** `{x.formula}`", f"- **Source:** {x.source}",
                f"- **Grain:** {x.grain}", f"- **Unit:** {x.unit}"]
        if x.assumptions:
            out.append(f"- **Assumptions:** {x.assumptions}")
        if x.limitations:
            out.append(f"- **Limitations:** {x.limitations}")
        out.append("")
    path.write_text("\n".join(out))


def write_quality_md(reports, manifest, profile, recon, recon_ids) -> None:  # type: ignore[no-untyped-def]
    out = ["# Data quality summary", "",
           f"Dataset {manifest['dataset']} v{manifest['dataset_version']}, source commit "
           f"`{manifest['source_commit']}`, fingerprint `{manifest['fingerprint']}`.", "",
           "## Acquisition", "",
           f"- Tables catalogued: {len(manifest['tables'])}; verified against official "
           f"SHA-256: {sum(t['status'] == 'verified' for t in manifest['tables'])}",
           f"- Missing required: {manifest['missing_required'] or 'none'}; missing optional: "
           f"{manifest['missing_optional'] or 'none'}", "",
           "## Tables", "",
           "| table | rows | cols | grain | duplicate keys | date coverage |",
           "|---|---|---|---|---|---|"]
    for t in profile["tables"]:
        cov = "; ".join(f"{k}: {v['min'][:10]}..{v['max'][:10]}"
                        for k, v in t["date_coverage"].items())
        out.append(f"| {t['table']} | {t['rows']:,} | {t['column_count']} | "
                   f"{t['documented_grain']} | {t['duplicate_key_groups']} | {cov} |")
    classes = ["confirmed_error", "potential_anomaly", "unverified_assumption",
               "expected_behavior"]
    out += ["", "## Findings by class", ""]
    for c in classes:
        items = [(t["table"], f) for t in profile["tables"] for f in t["findings"]
                 if f["class"] == c]
        extra = ["- M-1158 payout frequency far above game math (analytical findings, "
                 "section 2): the records are internally consistent, so this is a business "
                 "anomaly to inspect, not a data error."] if c == "potential_anomaly" else []
        out.append(f"### {c.replace('_', ' ').title()} ({len(items) + len(extra)})")
        out += extra
        for tbl, f in items[:40]:
            out.append(f"- `{tbl}.{f['column']}`: {f['detail']}")
        out.append("")
    out += ["## Referential integrity", "", "| child | parent | checked | orphans | status |",
            "|---|---|---|---|---|"]
    for r in profile["referential_integrity"]:
        out.append(f"| {r['child']} | {r['parent']} | {r['checked_rows']:,} | {r['orphans']} | "
                   f"{r['status']} |")
    out += ["", "## Join cardinality risks", "", "| join | left rows | joined rows | fan-out | "
            "safe |", "|---|---|---|---|---|"]
    for r in profile["join_cardinality"]:
        out.append(f"| {r['join']} | {r['left_rows']:,} | {r['joined_rows']:,} | "
                   f"{r['fan_out']} | {r['safe']} |")
    out += ["", "## Financial reconciliation", "",
            "| test | description | status | tolerance | evidence |", "|---|---|---|---|---|"]
    for r in recon:
        out.append(f"| {r.test_id} | {r.description} | **{r.status}** | {r.tolerance} | "
                   f"`{recon_ids[r.test_id]}` |")
    out += ["", "Full inputs and calculated values: `reports/reconciliation.json`."]
    (reports / "data_quality_summary.md").write_text("\n".join(out) + "\n")


def write_machine_md(reports, cmp, lists, persist, ids, decomp) -> None:  # type: ignore[no-untyped-def]
    cols = ["machine_id", "zone_id", "config_id", "house_win_usd", "active_days",
            "availability_rate", "luck_z", "hit_rate_z_cfg", "theo_per_available_hour",
            "rank_raw", "rank_exposure_adjusted", "rank_luck_aware", "rank_vs_peers",
            "p_bottom_luck_aware", "explanation"]
    rc = cmp.rank_changes[cols].copy()
    out = ["# Machine comparison (first pass)", "",
           f"Reference machine: median theo per available hour "
           f"${cmp.reference_rate:.2f} x median {cmp.reference_hours:,.0f} available hours.",
           "", "## Bottom-10 lists", ""]
    for k, v in lists.items():
        out.append(f"- **{k}** (`{ids[k]}`): {', '.join(v)}")
    out += ["", "## Ranking changes (machines in any bottom-10)", "", _md_table(rc.round(3)),
            "", "## Raw bottom-10 shortfall decomposition (sum over 10 machines, USD)", "",
            f"Evidence `{ids['decomposition']}`", ""]
    out += [f"- {k.removeprefix('gap_').removesuffix('_usd')}: ${v:,.0f}"
            for k, v in decomp.items()]
    out += ["", "## Zones", "", _md_table(cmp.zones.round(2)), "",
            f"## Persistence test (`{ids['persistence']}`)", "",
            "```json", json.dumps(persist, indent=1), "```", ""]
    (reports / "machine_comparison.md").write_text("\n".join(out) + "\n")


def write_findings_md(reports, cmp, lists, persist, inv, inv_ids, mc_ids, decomp, recon,  # type: ignore[no-untyped-def]
                      split, manifest) -> None:
    m = cmp.machines.set_index("machine_id")
    pa, wc = inv["payout_anomaly"], inv["walkway_closure"]
    dt, cr = inv["downtime_by_manufacturer"], inv["comp_rate_change"]
    raw = lists["raw"]
    in_b40 = int(sum(m.loc[i, "zone_id"] == "Z-B40" for i in raw))
    exposure = [i for i in raw if "limited_exposure" in m.loc[i, "explanation"]]
    anomaly = [i for i in raw if "payout_anomaly" in m.loc[i, "explanation"]]
    kept = sorted(set(raw) & set(lists["luck_aware"]))
    cfg_low = int(sum("low_theo_game_config" in m.loc[i, "explanation"] for i in raw))
    peer_ok = int(sum(m.loc[i, "machine_vs_peer_index"] >= 0.9 for i in raw))
    leak = pa["flagged"][0] if pa["flagged"] else None
    rr = cr["points_per_comp_usd_by_tier"]
    rid = dt["poisson_rate_ratios"]
    ridge = next(v for k, v in rid.items() if "Ridgeline" in k)
    passed = sum(r.status == "pass" for r in recon)
    out = [
        "# Analytical findings: Phase 1, Step 1", "",
        f"All numbers come from the official dataset v{manifest['dataset_version']} "
        f"(fingerprint `{manifest['fingerprint']}`) and are regenerated by "
        "`uv run python scripts/run_step1.py`. Evidence IDs point to "
        "`data/processed/evidence_ledger.jsonl`.", "",
        "## 0. The money reconciles",
        f"{passed} of {len(recon)} reconciliation checks pass (`reports/reconciliation.json`). "
        "House win equals coin-in minus payout to the cent; costs recompute from cost_rules; "
        "carded play agrees across three tables; comp cost is counted once.", "",
        "## 1. The manager's bottom 10 mixes four different problems",
        f"Raw bottom 10 (`{mc_ids['raw']}`): {', '.join(raw)}.", "",
        f"- **Location:** {in_b40} of 10 sit in Back Forty, the lowest-demand zone "
        f"(${cmp.zones.iloc[0].zone_theo_per_available_hour:.2f} theo per available hour "
        f"vs the ${cmp.reference_rate:.2f} floor median).",
        "- **Exposure:** " + "; ".join(
            f"{i} ({int(m.loc[i, 'active_days'])} active days, luck-free demand rank "
            f"#{int(m.loc[i, 'rank_luck_aware'])} of {len(m)})" for i in exposure) +
        ". Short tenure explains the low total only where the per-hour rank is not also low.",
        f"- **Payout anomaly:** {', '.join(anomaly) or 'none'}: demand ranks "
        f"#{int(m.loc[anomaly[0], 'rank_luck_aware']) if anomaly else '-'} of 310 on a "
        "luck-free basis; its win is low because it pays out too often (finding 2).",
        f"- **Game configuration:** {cfg_low} of the raw 10 run configurations whose "
        "same-zone peers earn under 80% of the zone rate (low house edge or small bets); "
        f"{peer_ok} of 10 earn at least 90% of their same-config, same-zone peers.",
        f"- Shortfall decomposition summed over the raw 10 (`{mc_ids['decomposition']}`): " +
        ", ".join(f"{k.removeprefix('gap_').removesuffix('_usd')} ${v:,.0f}"
                  for k, v in decomp.items()) + ".",
        f"- Machines in both the raw and luck-aware bottom 10: {', '.join(kept)}.",
        "",
        "**Competing explanation tested: luck.** If the raw ranking were mostly luck, the "
        "Q1 bottom 10 would regress toward the middle in Q2. "
        f"(`{mc_ids['persistence']}`): the Q1 raw bottom 10 averaged the "
        f"{persist['rankings']['raw_house_win']['h2_mean_win_percentile']:.0%} percentile "
        f"of Q2 win per available hour; the luck-aware bottom 10 averaged "
        f"{persist['rankings']['theo_per_available_hour']['h2_mean_win_percentile']:.0%}. "
        f"Quarter-to-quarter rank correlation: theo/hour "
        f"{persist['spearman_h1_h2_theo_per_ah']}, win/hour "
        f"{persist['spearman_h1_h2_win_per_ah']}. Low demand is persistent; luck is not the "
        "main driver, but the luck-free ranking is the more reliable one.", "",
    ]
    if leak:
        out += [
            f"## 2. {leak['machine_id']} pays out far more often than its game math allows "
            f"(`{inv_ids['payout_anomaly']}`)",
            f"Configured hit probability {leak['configured_hit_probability']:.1%}, observed "
            f"{leak['observed_hit_rate']:.1%} over {leak['paid_spins']:,} spins "
            f"(z = {leak['hit_rate_z']}); |z| > 3 in {leak['months_with_abs_hit_z_gt_3']} of "
            f"{leak['months_observed']} months. Observed hold {leak['observed_hold']:.1%} vs "
            f"configured {leak['configured_hold']:.0%}; shortfall vs theo "
            f"${leak['house_win_shortfall_vs_theo_usd']:,.0f} "
            f"(${leak['shortfall_per_active_day_usd']:.0f}/day).",
            f"- Competing explanation (luck): rejected. Hit counts are not driven by jackpot "
            f"size; the other {pa['machines_tested'] - 1} machines' hit z-scores have SD "
            f"{pa['other_machines_hit_z_sd']} (calibrated).",
            "- Decision relevance: an inspection ($1,200) is the matching action; replacing "
            "the machine would hide the cause. Cause (paytable vs meter/software) unverified.",
            ""]
    out += [
        f"## 3. The walkway closure cut Back Forty demand by about "
        f"{-wc['closure_effect_pct']:.0f}% (`{inv_ids['walkway_closure']}`)",
        f"{wc['observation']} Relative to the rest of the floor (fixed machines, weekday "
        f"adjusted), Back Forty theo per available hour changed {wc['closure_effect_pct']}% "
        f"(95% CI {wc['closure_effect_ci95_pct'][0]}% to {wc['closure_effect_ci95_pct'][1]}%); "
        f"after reopening {wc['post_vs_pre_pct']}% (p = {wc['post_p_value']:.2f}). Estimated "
        f"lost theo ${wc['estimated_lost_theo_usd']:,.0f} "
        f"(CI ${wc['estimated_lost_theo_ci95_usd'][0]:,.0f}-"
        f"${wc['estimated_lost_theo_ci95_usd'][1]:,.0f}).",
        f"- Competing explanation (floor-wide seasonality): controlled by the ratio design. "
        f"Traffic counters agree: Back Forty's share of entries fell to "
        f"{wc['traffic_entries_ratio_target_vs_rest_by_period']['closure']} of the rest "
        f"(pre {wc['traffic_entries_ratio_target_vs_rest_by_period']['pre']}).",
        "- Decision relevance: half-year rankings understate Back Forty machines for a "
        "resolved, temporary cause. Back Forty is still the weakest zone before the closure, "
        "so access/visibility, not the machines, is the lever to test (e.g. wayfinding).",
        "- Uncertainty: one event; the HAC interval assumes the rest of the floor is a valid "
        "control.", "",
        f"## 4. Ridgeline machines fail about {ridge['rate_ratio']:.1f}x as often as Halcyon "
        f"(`{inv_ids['downtime_by_manufacturer']}`)",
        f"Poisson rate ratio {ridge['rate_ratio']} (95% CI {ridge['ci95'][0]}-"
        f"{ridge['ci95'][1]}) after controlling for machine age (competing explanation: "
        f"age; age matters but does not explain it). Floor downtime is only "
        f"{dt['floor_downtime_share']:.2%}; Ridgeline's excess costs about "
        f"${dt['excess_lost_theo_per_30d_usd']:,.0f} theo per 30 days.",
        "- Decision relevance: a $9,000 preventive sweep (7-day lead) would have to remove "
        "nearly all excess downtime to break even on theo within July; sensitivity needed "
        "in Step 2.", "",
        f"## 5. The comp program got cheaper for guests on {cr['change_point_gaming_date']} "
        f"(`{inv_ids['comp_rate_change']}`)",
        "Points needed per comp dollar, pre -> post: " +
        "; ".join(f"{t['tier']} {t['pre']:.1f} -> {t['post']:.1f}" for t in rr) + ".",
        "- Competing explanation (tier mix): rejected; the rate halves within every tier.",
        f"- Comp cost per day ${cr['comp_cost_per_day_pre_usd']:,.0f} -> "
        f"${cr['comp_cost_per_day_post_usd']:,.0f} ({cr['comp_cost_change_pct']:+.1f}%); "
        f"per carded theo {cr['comp_cost_per_carded_theo_pre']:.2%} -> "
        f"{cr['comp_cost_per_carded_theo_post']:.2%}.",
        "- Decision relevance: answers Q5 ('did anything change'). Whether the cheaper "
        "comps bought extra play is untested; that is what A-COMP-PILOT would measure.", "",
        "## 6. Modeling preparation",
        "Target daily floor coin-in; splits: " +
        "; ".join(f"{k} {v['first']}..{v['last']} ({v['days']} days)" for k, v in
                  split.items()) + ". See `docs/MODELING_PLAN.md`.", "",
        "## Limitations",
        "- Synthetic world; values may change before release 1.0.0.",
        "- Theo per available hour mixes location, game configuration and player mix.",
        "- Lost-theo estimates assume downtime/closure hours would be played at average rates.",
        "- No finding here is a funded recommendation; pricing and optimisation are Step 2+.",
    ]
    (reports / "analytical_findings.md").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
