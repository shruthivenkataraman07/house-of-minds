import { loadDataset, loadManifest } from "@/lib/data";

/**
 * Preflight starter page (not the final dashboard): proves the verified snapshot loads,
 * validates and renders in a production build. Values are read from Databricks exports.
 */
const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export default async function Home() {
  "use cache"; // snapshot is immutable per export: cache the verified render (Next 16)
  const manifest = loadManifest();
  const kpis = loadDataset("dash_executive_kpis");
  const passports = loadDataset("dash_decision_passports");
  const claims = loadDataset("dash_evidence_validation");
  const k = Object.fromEntries(kpis.map((r) => [r.kpi, r.value]));
  const portfolios = [
    ["Evidence-supported", k.evidence_portfolio_cost, k.evidence_portfolio_modeled_net],
    ["Conditional", k.conditional_portfolio_cost, k.conditional_portfolio_modeled_net],
  ] as const;

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 font-sans text-zinc-900 dark:text-zinc-100">
      <p className="text-xs uppercase tracking-widest text-zinc-500">Preflight build</p>
      <h1 className="mt-1 text-3xl font-semibold">The House of Minds</h1>
      <p className="mt-2 text-sm text-zinc-500">
        Snapshot <code>{manifest.snapshot_id}</code> · exported {manifest.exported_at_utc} ·{" "}
        {manifest.files.length} verified datasets
      </p>

      <section className="mt-8 grid gap-4 sm:grid-cols-3">
        <Stat label="Coin-in (Jan–Jun 2025)" value={usd(k.coin_in_usd)} />
        <Stat label="House win" value={usd(k.house_win_usd)} />
        <Stat label="Reconciliation checks" value={`${k.reconciliation_checks_passed}/14 pass`} />
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-medium">$100K portfolios (modeled, not realised)</h2>
        <ul className="mt-3 divide-y divide-zinc-200 dark:divide-zinc-800">
          {portfolios.map(([name, cost, net]) => (
            <li key={name} className="flex justify-between py-2 text-sm">
              <span>{name}</span>
              <span className="tabular-nums">
                cost {usd(cost)} · modeled net {usd(net)}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <p className="mt-8 text-sm text-zinc-500">
        {passports.length} decision passports · {claims.length} evidence-linked claims · full
        dashboard coming in the final build.
      </p>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
