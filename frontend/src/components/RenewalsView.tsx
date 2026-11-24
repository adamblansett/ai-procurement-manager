import { type FormEvent, useEffect, useState } from 'react';
import { CalendarPlus, Copy, Send, Sparkles } from 'lucide-react';
import { procurementApi } from '../api/client';
import type { Contract, RenewalBriefResponse, RenewalItem, Vendor } from '../types/procurement';
import { formatCurrency, formatLabel, getBadgeTone } from '../utils/format';

interface RenewalsViewProps {
  vendors: Vendor[];
  onDataChange: () => Promise<void>;
}

export function RenewalsView({ vendors, onDataChange }: RenewalsViewProps) {
  const [renewals, setRenewals] = useState<RenewalItem[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [selected, setSelected] = useState<RenewalItem | null>(null);
  const [brief, setBrief] = useState<RenewalBriefResponse | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  const [vendorId, setVendorId] = useState('');
  const [contractId, setContractId] = useState('');
  const [contractTitle, setContractTitle] = useState('');
  const [renewalDate, setRenewalDate] = useState('2027-02-15');
  const [noticeDays, setNoticeDays] = useState('60');
  const [autoRenew, setAutoRenew] = useState(true);
  const [annualValue, setAnnualValue] = useState('95000');
  const [upliftPct, setUpliftPct] = useState('7.5');
  const [ownerName, setOwnerName] = useState('Samira Chen');

  const [actionNotes, setActionNotes] = useState('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadRenewals(selectId?: string) {
    try {
      const [items, contractList] = await Promise.all([
        procurementApi.listRenewals(),
        procurementApi.listContracts(),
      ]);
      setRenewals(items);
      setContracts(contractList);
      const target = items.find((r) => r.id === (selectId || selected?.id)) || items[0] || null;
      setSelected(target);
      if (target && target.brief_data_json && Object.keys(target.brief_data_json).length > 0) {
        const d = target.brief_data_json;
        setBrief({
          renewal: target,
          projected_value: Number(d.projected_value ?? target.projected_renewal_value),
          target_value: Number(d.target_value ?? target.current_annual_value),
          estimated_annual_savings: Number(d.estimated_annual_savings ?? 0),
          three_year_savings: Number(d.three_year_savings ?? 0),
          leverage_points: (d.leverage_points as string[]) || [],
          clause_redlines: (d.clause_redlines as string[]) || [],
          recommended_timeline: (d.recommended_timeline as string[]) || [],
          draft_notice_email: String(d.draft_notice_email ?? ''),
          brief_markdown: target.brief_markdown,
        });
      } else if (selectId || !selected) {
        setBrief(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load renewals');
    }
  }

  useEffect(() => {
    void loadRenewals();
  }, []);

  useEffect(() => {
    if (!vendorId && vendors.length > 0) {
      setVendorId(vendors[0].id);
    }
  }, [vendors, vendorId]);

  function handleSelectRenewal(item: RenewalItem) {
    setSelected(item);
    setStatusMessage(null);
    setError(null);
    if (item.brief_data_json && Object.keys(item.brief_data_json).length > 0) {
      const d = item.brief_data_json;
      setBrief({
        renewal: item,
        projected_value: Number(d.projected_value ?? item.projected_renewal_value),
        target_value: Number(d.target_value ?? item.current_annual_value),
        estimated_annual_savings: Number(d.estimated_annual_savings ?? 0),
        three_year_savings: Number(d.three_year_savings ?? 0),
        leverage_points: (d.leverage_points as string[]) || [],
        clause_redlines: (d.clause_redlines as string[]) || [],
        recommended_timeline: (d.recommended_timeline as string[]) || [],
        draft_notice_email: String(d.draft_notice_email ?? ''),
        brief_markdown: item.brief_markdown,
      });
    } else {
      setBrief(null);
    }
  }

  async function handleGenerateBrief() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const result = await procurementApi.generateRenewalBrief(selected.id);
      setBrief(result);
      setSelected(result.renewal);
      setStatusMessage(
        `Generated AI renegotiation dossier (${formatCurrency(result.estimated_annual_savings)}/yr target savings).`
      );
      await loadRenewals(result.renewal.id);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate brief');
    } finally {
      setBusy(false);
    }
  }

  async function handleRequestAction(
    actionType: 'send_non_renewal_notice' | 'approve_renewal_terms'
  ) {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const res = await procurementApi.requestRenewalAction(
        selected.id,
        actionType,
        selected.owner_name,
        actionNotes || 'Requested via Renewal Calendar.'
      );
      setStatusMessage(
        `Queued HITL approval (${formatLabel(res.required_role)}) — no notice sent until approved.`
      );
      setActionNotes('');
      await loadRenewals(selected.id);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to queue renewal approval');
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateRenewal(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await procurementApi.createRenewal({
        vendor_id: vendorId,
        contract_id: contractId || null,
        contract_title: contractTitle,
        renewal_date: renewalDate,
        notice_period_days: Number(noticeDays) || 60,
        auto_renew: autoRenew,
        current_annual_value: Number(annualValue),
        proposed_uplift_pct: Number(upliftPct) || 0,
        owner_name: ownerName,
      });
      setShowAdd(false);
      setContractTitle('');
      await loadRenewals(created.id);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create renewal');
    } finally {
      setBusy(false);
    }
  }

  function handleCopyDraft() {
    if (!brief?.draft_notice_email) return;
    if (navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(brief.draft_notice_email);
    }
    setStatusMessage('Draft notice text copied to clipboard (still requires HITL approval before sending).');
  }

  const counts = {
    overdue: renewals.filter((r) => r.urgency === 'overdue').length,
    critical: renewals.filter((r) => r.urgency === 'critical').length,
    upcoming: renewals.filter((r) => r.urgency === 'upcoming').length,
    healthy: renewals.filter((r) => r.urgency === 'healthy').length,
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Renewal Calendar &amp; Renegotiation Briefs
          </h2>
          <p className="text-xs text-slate-600">
            Track auto-renewal notice cutoffs, assemble contract + benchmark leverage, and gate
            outbound notices via HITL approval.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAdd((prev) => !prev)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
        >
          <CalendarPlus className="h-3.5 w-3.5" />
          Track New Renewal
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-xs text-rose-800">
          {error}
        </div>
      )}
      {statusMessage && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs text-emerald-800">
          {statusMessage}
        </div>
      )}

      <section className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4">
          <p className="text-[11px] font-semibold uppercase text-rose-700">Overdue Notice</p>
          <p className="mt-1 text-2xl font-bold text-rose-900">{counts.overdue}</p>
        </div>
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-[11px] font-semibold uppercase text-amber-800">Critical (&le; 30d)</p>
          <p className="mt-1 text-2xl font-bold text-amber-900">{counts.critical}</p>
        </div>
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4">
          <p className="text-[11px] font-semibold uppercase text-indigo-800">Upcoming (&le; 90d)</p>
          <p className="mt-1 text-2xl font-bold text-indigo-900">{counts.upcoming}</p>
        </div>
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <p className="text-[11px] font-semibold uppercase text-emerald-800">Healthy / Resolved</p>
          <p className="mt-1 text-2xl font-bold text-emerald-900">{counts.healthy}</p>
        </div>
      </section>

      {showAdd && (
        <form
          onSubmit={(e) => void handleCreateRenewal(e)}
          className="grid gap-3 rounded-xl border border-indigo-200 bg-white p-5 shadow-sm sm:grid-cols-4"
        >
          <label className="text-xs">
            <span className="font-medium text-slate-700">Vendor</span>
            <select
              value={vendorId}
              onChange={(e) => setVendorId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            >
              {vendors.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs sm:col-span-2">
            <span className="font-medium text-slate-700">Agreement Title</span>
            <input
              value={contractTitle}
              onChange={(e) => setContractTitle(e.target.value)}
              placeholder="e.g. Annual SaaS Enterprise Order"
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Linked Contract</span>
            <select
              value={contractId}
              onChange={(e) => setContractId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            >
              <option value="">None</option>
              {contracts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Renewal Date</span>
            <input
              type="date"
              value={renewalDate}
              onChange={(e) => setRenewalDate(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Notice Period (Days)</span>
            <input
              type="number"
              value={noticeDays}
              onChange={(e) => setNoticeDays(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Current Annual Value ($)</span>
            <input
              type="number"
              value={annualValue}
              onChange={(e) => setAnnualValue(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs">
              <span className="font-medium text-slate-700">Uplift %</span>
              <input
                type="number"
                step="0.1"
                value={upliftPct}
                onChange={(e) => setUpliftPct(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
              />
            </label>
            <label className="text-xs">
              <span className="font-medium text-slate-700">Owner</span>
              <input
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
                required
              />
            </label>
          </div>
          <div className="flex items-center justify-between sm:col-span-4">
            <label className="inline-flex items-center gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                checked={autoRenew}
                onChange={(e) => setAutoRenew(e.target.checked)}
              />
              Auto-renews unless timely written non-renewal notice is sent
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowAdd(false)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy}
                className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
              >
                Save Renewal
              </button>
            </div>
          </div>
        </form>
      )}

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="space-y-2.5 lg:col-span-5">
          {renewals.map((item) => {
            const active = selected?.id === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => handleSelectRenewal(item)}
                className={`w-full rounded-xl border p-4 text-left transition ${
                  active
                    ? 'border-indigo-500 bg-indigo-50/40 ring-1 ring-indigo-500'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-xs font-semibold text-slate-900">{item.contract_title}</p>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {item.vendor_name} &middot; {formatCurrency(item.current_annual_value)}/yr
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getBadgeTone(item.urgency)}`}
                  >
                    {item.days_to_notice_deadline}d left
                  </span>
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                  <span>
                    Notice: {item.notice_deadline} &middot; +{item.proposed_uplift_pct}% uplift
                  </span>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${getBadgeTone(item.decision_status)}`}
                  >
                    {formatLabel(item.decision_status)}
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        <div className="lg:col-span-7">
          {selected ? (
            <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
                <div>
                  <h3 className="text-base font-bold text-slate-900">{selected.contract_title}</h3>
                  <p className="mt-1 text-xs text-slate-500">
                    {selected.vendor_name} &middot; Owner: {selected.owner_name} &middot; Notice
                    Deadline: <strong className="text-slate-800">{selected.notice_deadline}</strong>{' '}
                    ({selected.auto_renew ? 'Auto-Renew' : 'Opt-In'})
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleGenerateBrief()}
                  disabled={busy}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  {busy ? 'Generating...' : 'Generate AI Renegotiation Brief'}
                </button>
              </div>

              {brief ? (
                <div className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="rounded-lg bg-slate-50 p-3">
                      <p className="text-[11px] text-slate-500">Projected Uplift Value</p>
                      <p className="mt-1 text-sm font-bold text-slate-900">
                        {formatCurrency(brief.projected_value)}
                      </p>
                    </div>
                    <div className="rounded-lg bg-indigo-50 p-3">
                      <p className="text-[11px] text-indigo-700">Target Renewal Value</p>
                      <p className="mt-1 text-sm font-bold text-indigo-900">
                        {formatCurrency(brief.target_value)}
                      </p>
                    </div>
                    <div className="rounded-lg bg-emerald-50 p-3">
                      <p className="text-[11px] text-emerald-700">Estimated Annual Savings</p>
                      <p className="mt-1 text-sm font-bold text-emerald-800">
                        {formatCurrency(brief.estimated_annual_savings)}{' '}
                        <span className="text-[10px] font-normal">
                          (3yr: {formatCurrency(brief.three_year_savings)})
                        </span>
                      </p>
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="rounded-lg border border-slate-200 p-3.5">
                      <h4 className="text-xs font-semibold text-slate-900">
                        Commercial &amp; Pricing Leverage
                      </h4>
                      <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-slate-700">
                        {brief.leverage_points.map((pt, i) => (
                          <li key={i}>{pt}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="rounded-lg border border-slate-200 p-3.5">
                      <h4 className="text-xs font-semibold text-slate-900">
                        Recommended Contract Redlines
                      </h4>
                      <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-slate-700">
                        {brief.clause_redlines.map((redline, i) => (
                          <li key={i}>{redline}</li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3.5">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-semibold text-slate-900">
                        Draft Notice Email (HITL Approval Required Before Sending)
                      </h4>
                      <button
                        type="button"
                        onClick={handleCopyDraft}
                        className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 hover:text-indigo-800"
                      >
                        <Copy className="h-3 w-3" />
                        Copy Draft
                      </button>
                    </div>
                    <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px] text-slate-700">
                      {brief.draft_notice_email}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-xs text-slate-500">
                  Click <strong>Generate AI Renegotiation Brief</strong> to combine linked contract
                  playbook deviations, benchmark percentiles, and notice-window leverage.
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                <input
                  value={actionNotes}
                  onChange={(e) => setActionNotes(e.target.value)}
                  placeholder="Optional HITL reviewer instructions..."
                  className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                />
                <button
                  type="button"
                  onClick={() => void handleRequestAction('send_non_renewal_notice')}
                  disabled={busy}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100"
                >
                  <Send className="h-3.5 w-3.5" />
                  Request Non-Renewal Notice Approval
                </button>
                <button
                  type="button"
                  onClick={() => void handleRequestAction('approve_renewal_terms')}
                  disabled={busy}
                  className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
                >
                  Approve Renewal Terms
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-xs text-slate-500">
              Select a renewal item to view or generate its renegotiation dossier.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
