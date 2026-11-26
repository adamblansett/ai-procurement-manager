import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Database,
  FileWarning,
  ShieldCheck,
  TrendingDown,
} from 'lucide-react';
import type { ApprovalRequest, DashboardSummary } from '../types/procurement';
import { formatCurrency, formatLabel, getBadgeTone } from '../utils/format';

export type WorkspaceTab =
  | 'overview'
  | 'vendors'
  | 'contracts'
  | 'benchmarks'
  | 'purchasing'
  | 'renewals'
  | 'governance';

interface OverviewDashboardProps {
  summary: DashboardSummary | null;
  approvals: ApprovalRequest[];
  loading: boolean;
  onNavigate: (tab: WorkspaceTab) => void;
  onSeedDemo: () => Promise<void>;
}

export function OverviewDashboard({
  summary,
  approvals,
  loading,
  onNavigate,
  onSeedDemo,
}: OverviewDashboardProps) {
  if (loading && !summary) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
        Loading procurement telemetry...
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
        Unable to reach the procurement backend API. Start the FastAPI server on port 8000 to load
        live contracts, benchmarks, PO validation, and governance data.
      </div>
    );
  }

  const maxCategorySpend = Math.max(
    1,
    ...summary.spend_by_category.map((item) => item.annual_spend)
  );
  const pendingApprovals = approvals.filter((a) => a.status === 'pending').slice(0, 4);

  return (
    <div className="space-y-6">
      {summary.total_vendors === 0 && (
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-indigo-200 bg-indigo-50 px-5 py-4">
          <div className="flex items-center gap-3">
            <Database className="h-5 w-5 text-indigo-600" />
            <div>
              <p className="text-sm font-semibold text-indigo-950">Empty Workspace</p>
              <p className="text-xs text-indigo-800">
                Populate realistic enterprise vendors, contracts, benchmarks, POs, and renewals.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void onSeedDemo()}
            className="rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-indigo-700"
          >
            Load Demo Data
          </button>
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Managed Annual Spend</span>
            <TrendingDown className="h-4 w-4 text-indigo-600" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {formatCurrency(summary.total_annual_spend)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Across {summary.total_vendors} suppliers &middot; {summary.benchmarks_count} price benchmarks
          </p>
        </div>

        <button
          type="button"
          onClick={() => onNavigate('contracts')}
          className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-indigo-300"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Contracts &amp; Risk Score</span>
            <FileWarning className="h-4 w-4 text-amber-600" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {summary.active_contracts}{' '}
            <span className="text-sm font-medium text-slate-500">
              ({summary.high_risk_contracts} high-risk)
            </span>
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Avg playbook risk score: {summary.avg_contract_risk_score}/100
          </p>
        </button>

        <button
          type="button"
          onClick={() => onNavigate('governance')}
          className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-indigo-300"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Pending HITL Approvals</span>
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
          </div>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {summary.pending_approvals_count}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {summary.open_pos_count} open POs &middot; {summary.blocked_pos_count} blocked by rules
          </p>
        </button>

        <button
          type="button"
          onClick={() => onNavigate('renewals')}
          className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-indigo-300"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Savings &amp; Urgent Renewals</span>
            <CalendarClock className="h-4 w-4 text-rose-600" />
          </div>
          <p className="mt-2 text-2xl font-bold text-emerald-700">
            {formatCurrency(summary.estimated_savings_opportunity)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {summary.urgent_renewals_count} renewals inside 90-day notice window
          </p>
        </button>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Spend by Category</h2>
            <button
              type="button"
              onClick={() => onNavigate('benchmarks')}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
            >
              Benchmark Rates &rarr;
            </button>
          </div>
          <div className="mt-4 space-y-3">
            {summary.spend_by_category.map((cat) => {
              const pct = Math.round((cat.annual_spend / maxCategorySpend) * 100);
              return (
                <div key={cat.category}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-700">
                      {cat.category}{' '}
                      <span className="text-slate-400">({cat.vendor_count})</span>
                    </span>
                    <span className="font-semibold text-slate-900">
                      {formatCurrency(cat.annual_spend)}
                    </span>
                  </div>
                  <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-indigo-600"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Urgent Renewal Notice Deadlines</h2>
            <button
              type="button"
              onClick={() => onNavigate('renewals')}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
            >
              Open Calendar &rarr;
            </button>
          </div>
          <div className="mt-4 space-y-2.5">
            {summary.urgent_renewals.length === 0 ? (
              <p className="text-xs text-slate-500">No urgent renewals within 90 days.</p>
            ) : (
              summary.urgent_renewals.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3.5 py-2.5"
                >
                  <div>
                    <p className="text-xs font-semibold text-slate-900">
                      {item.vendor_name} &mdash; {item.contract_title}
                    </p>
                    <p className="text-[11px] text-slate-500">
                      Notice deadline {item.notice_deadline} &middot;{' '}
                      {formatCurrency(item.current_annual_value)}/yr (+{item.proposed_uplift_pct}% proposed)
                    </p>
                  </div>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${getBadgeTone(item.urgency)}`}
                  >
                    {item.days_to_notice_deadline}d ({formatLabel(item.urgency)})
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Human-in-the-Loop Approval Queue</h2>
            <button
              type="button"
              onClick={() => onNavigate('governance')}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
            >
              Review Queue &rarr;
            </button>
          </div>
          <div className="mt-4 space-y-2.5">
            {pendingApprovals.length === 0 ? (
              <div className="flex items-center gap-2 text-xs text-emerald-700">
                <CheckCircle2 className="h-4 w-4" />
                All approval gates are cleared.
              </div>
            ) : (
              pendingApprovals.map((app) => (
                <div
                  key={app.id}
                  className="flex items-start justify-between gap-3 rounded-lg border border-amber-100 bg-amber-50/50 px-3.5 py-2.5"
                >
                  <div>
                    <p className="text-xs font-semibold text-slate-900">{app.title}</p>
                    <p className="mt-0.5 text-[11px] text-slate-600">{app.summary}</p>
                  </div>
                  <span className="shrink-0 rounded-full border border-amber-200 bg-white px-2 py-0.5 text-[11px] font-medium text-amber-800">
                    {formatLabel(app.required_role)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Recent Immutable Audit Events</h2>
            <button
              type="button"
              onClick={() => onNavigate('governance')}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
            >
              Verify Hash Chain &rarr;
            </button>
          </div>
          <div className="mt-4 space-y-2">
            {summary.recent_audit_logs.map((entry) => (
              <div
                key={entry.sequence_num}
                className="flex items-center justify-between gap-3 border-b border-slate-100 pb-2 text-xs last:border-b-0 last:pb-0"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] text-slate-400">
                      #{entry.sequence_num}
                    </span>
                    <span className="font-semibold text-slate-800">{entry.action}</span>
                    <span className="text-slate-400">by {entry.actor}</span>
                  </div>
                  <p className="truncate text-[11px] text-slate-600">{entry.summary}</p>
                </div>
                <span className="shrink-0 font-mono text-[10px] text-slate-400">
                  {entry.entry_hash.slice(0, 10)}...
                </span>
              </div>
            ))}
            {summary.blocked_pos_count > 0 && (
              <button
                type="button"
                onClick={() => onNavigate('purchasing')}
                className="mt-2 flex w-full items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-medium text-rose-800 hover:bg-rose-100"
              >
                <span className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  {summary.blocked_pos_count} Purchase Order(s) blocked by quote/budget rules
                </span>
                <span>Inspect &rarr;</span>
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
