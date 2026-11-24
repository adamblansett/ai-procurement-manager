import { type ChangeEvent, type FormEvent, useEffect, useState } from 'react';
import { BookOpen, FilePlus2, GitCompareArrows, RefreshCw, ShieldAlert } from 'lucide-react';
import { procurementApi } from '../api/client';
import type {
  Contract,
  ContractDetail,
  ContractPairComparison,
  PlaybookRule,
  Vendor,
} from '../types/procurement';
import { formatCurrency, formatLabel, getBadgeTone } from '../utils/format';

interface ContractsViewProps {
  vendors: Vendor[];
  onDataChange: () => Promise<void>;
}

export function ContractsView({ vendors, onDataChange }: ContractsViewProps) {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [playbooks, setPlaybooks] = useState<PlaybookRule[]>([]);
  const [selectedDetail, setSelectedDetail] = useState<ContractDetail | null>(null);
  const [mode, setMode] = useState<'detail' | 'pair' | 'playbooks'>('detail');
  const [showIngest, setShowIngest] = useState(false);

  const [leftId, setLeftId] = useState('');
  const [rightId, setRightId] = useState('');
  const [pairComparison, setPairComparison] = useState<ContractPairComparison | null>(null);

  const [vendorId, setVendorId] = useState('');
  const [title, setTitle] = useState('');
  const [contractType, setContractType] = useState('MSA');
  const [annualValue, setAnnualValue] = useState('120000');
  const [rawText, setRawText] = useState('');

  const [approvalNotes, setApprovalNotes] = useState('');
  const [requestedBy, setRequestedBy] = useState('Samira Chen');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadContracts(selectId?: string) {
    try {
      const [contractList, ruleList] = await Promise.all([
        procurementApi.listContracts(),
        procurementApi.listPlaybooks(),
      ]);
      setContracts(contractList);
      setPlaybooks(ruleList);

      const targetId = selectId || selectedDetail?.id || contractList[0]?.id;
      if (targetId) {
        const detail = await procurementApi.getContract(targetId);
        setSelectedDetail(detail);
      }
      if (contractList.length >= 2 && !leftId && !rightId) {
        setLeftId(contractList[0].id);
        setRightId(contractList[1].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load contracts');
    }
  }

  useEffect(() => {
    void loadContracts();
  }, []);

  useEffect(() => {
    if (!vendorId && vendors.length > 0) {
      setVendorId(vendors[0].id);
    }
  }, [vendors, vendorId]);

  async function handleSelectContract(id: string) {
    setMode('detail');
    setError(null);
    setStatusMessage(null);
    try {
      const detail = await procurementApi.getContract(id);
      setSelectedDetail(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load contract details');
    }
  }

  async function handleRecompare() {
    if (!selectedDetail) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await procurementApi.recompareContract(selectedDetail.id);
      setSelectedDetail(updated);
      setStatusMessage('Re-evaluated contract clauses against active playbook rules.');
      await loadContracts(updated.id);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Comparison failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleRequestApproval() {
    if (!selectedDetail) return;
    setBusy(true);
    setError(null);
    try {
      const res = await procurementApi.requestContractApproval(
        selectedDetail.id,
        requestedBy || 'Procurement Lead',
        approvalNotes || 'Playbook deviation sign-off requested.'
      );
      setStatusMessage(`Queued HITL approval (${formatLabel(res.required_role)}).`);
      setApprovalNotes('');
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to request approval');
    } finally {
      setBusy(false);
    }
  }

  async function handleComparePair() {
    if (!leftId || !rightId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await procurementApi.compareContractPair(leftId, rightId);
      setPairComparison(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Pair comparison failed');
    } finally {
      setBusy(false);
    }
  }

  function handleFileUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        setRawText(reader.result);
      }
    };
    reader.readAsText(file);
  }

  async function handleIngestSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await procurementApi.createContract({
        vendor_id: vendorId,
        title,
        contract_type: contractType,
        annual_value: Number(annualValue) || 0,
        raw_text: rawText,
        auto_compare: true,
      });
      setShowIngest(false);
      setTitle('');
      setRawText('');
      setSelectedDetail(created);
      setMode('detail');
      setStatusMessage(`Ingested & compared '${created.title}' (${created.risk_score}/100 risk).`);
      await loadContracts(created.id);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to ingest contract');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Contract Comparison &amp; Playbook Diffing
          </h2>
          <p className="text-xs text-slate-600">
            Compare vendor MSAs, DPAs, and order forms against preferred commercial terms.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setMode(mode === 'pair' ? 'detail' : 'pair')}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <GitCompareArrows className="h-3.5 w-3.5" />
            {mode === 'pair' ? 'Single Contract View' : 'Side-by-Side Diff'}
          </button>
          <button
            type="button"
            onClick={() => setMode(mode === 'playbooks' ? 'detail' : 'playbooks')}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <BookOpen className="h-3.5 w-3.5" />
            Playbook Rules ({playbooks.length})
          </button>
          <button
            type="button"
            onClick={() => setShowIngest((prev) => !prev)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
          >
            <FilePlus2 className="h-3.5 w-3.5" />
            Ingest &amp; Compare Contract
          </button>
        </div>
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

      {showIngest && (
        <form
          onSubmit={(e) => void handleIngestSubmit(e)}
          className="space-y-4 rounded-xl border border-indigo-200 bg-white p-5 shadow-sm"
        >
          <h3 className="text-sm font-semibold text-slate-900">Ingest Vendor Contract</h3>
          <div className="grid gap-3 sm:grid-cols-4">
            <label className="block text-xs">
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
            <label className="block text-xs sm:col-span-2">
              <span className="font-medium text-slate-700">Contract Title</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Acme SaaS Master Subscription Agreement"
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-xs">
                <span className="font-medium text-slate-700">Type</span>
                <select
                  value={contractType}
                  onChange={(e) => setContractType(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
                >
                  <option value="MSA">MSA</option>
                  <option value="DPA">DPA</option>
                  <option value="Order Form">Order Form</option>
                  <option value="SOW">SOW</option>
                </select>
              </label>
              <label className="block text-xs">
                <span className="font-medium text-slate-700">Annual ($)</span>
                <input
                  type="number"
                  value={annualValue}
                  onChange={(e) => setAnnualValue(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
                />
              </label>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-slate-700">
                Contract Clauses Text (paste or load .txt / .md)
              </span>
              <input
                type="file"
                accept=".txt,.md"
                onChange={handleFileUpload}
                className="text-[11px] text-slate-500"
              />
            </div>
            <textarea
              rows={5}
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              placeholder="Paste MSA clauses covering auto-renewal notice, uplift cap, liability cap, payment terms, DPA, indemnification, and SLA..."
              className="w-full rounded-lg border border-slate-200 p-2.5 font-mono text-xs"
              required
              minLength={10}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowIngest(false)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy ? 'Analyzing...' : 'Ingest & Run Playbook Diff'}
            </button>
          </div>
        </form>
      )}

      {mode === 'playbooks' ? (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-[11px] uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Clause Family</th>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Preferred Position</th>
                <th className="px-4 py-3">Fallback Position</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {playbooks.map((rule) => (
                <tr key={rule.id}>
                  <td className="px-4 py-3 font-semibold text-slate-900">
                    {rule.name}
                    <div className="font-mono text-[10px] text-slate-400">{rule.clause_type}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${getBadgeTone(rule.severity)}`}
                    >
                      {formatLabel(rule.severity)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-700">{rule.preferred_position}</td>
                  <td className="px-4 py-3 text-slate-500">{rule.fallback_position}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : mode === 'pair' ? (
        <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex-1 text-xs">
              <span className="font-medium text-slate-700">Baseline / Left Contract</span>
              <select
                value={leftId}
                onChange={(e) => setLeftId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs"
              >
                {contracts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.vendor_name} — {c.title} ({c.risk_score}/100)
                  </option>
                ))}
              </select>
            </label>
            <label className="flex-1 text-xs">
              <span className="font-medium text-slate-700">Comparison / Right Contract</span>
              <select
                value={rightId}
                onChange={(e) => setRightId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs"
              >
                {contracts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.vendor_name} — {c.title} ({c.risk_score}/100)
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void handleComparePair()}
              disabled={busy || !leftId || !rightId}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              Run Side-by-Side Diff
            </button>
          </div>

          {pairComparison && (
            <div className="space-y-3">
              <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2.5 text-xs font-medium text-indigo-950">
                {pairComparison.recommendation}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-[11px] uppercase text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Clause</th>
                      <th className="px-3 py-2">{pairComparison.left_contract.title}</th>
                      <th className="px-3 py-2">{pairComparison.right_contract.title}</th>
                      <th className="px-3 py-2">Delta</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {pairComparison.clause_diffs.map((diff) => (
                      <tr key={diff.clause_type}>
                        <td className="px-3 py-2.5 font-semibold text-slate-900">
                          {formatLabel(diff.clause_type)}
                        </td>
                        <td className="px-3 py-2.5">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getBadgeTone(diff.left_status)}`}
                          >
                            {formatLabel(diff.left_status)}
                          </span>
                          <p className="mt-1 text-[11px] text-slate-600">{diff.left_excerpt}</p>
                        </td>
                        <td className="px-3 py-2.5">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getBadgeTone(diff.right_status)}`}
                          >
                            {formatLabel(diff.right_status)}
                          </span>
                          <p className="mt-1 text-[11px] text-slate-600">{diff.right_excerpt}</p>
                        </td>
                        <td className="px-3 py-2.5 text-[11px] text-slate-700">
                          {diff.delta_summary}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-12">
          <div className="space-y-2.5 lg:col-span-4">
            {contracts.map((c) => {
              const active = selectedDetail?.id === c.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => void handleSelectContract(c.id)}
                  className={`w-full rounded-xl border p-4 text-left transition ${
                    active
                      ? 'border-indigo-500 bg-indigo-50/40 ring-1 ring-indigo-500'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-xs font-semibold text-slate-900">{c.title}</p>
                      <p className="mt-0.5 text-[11px] text-slate-500">
                        {c.vendor_name} &middot; {c.contract_type} &middot;{' '}
                        {formatCurrency(c.annual_value)}/yr
                      </p>
                    </div>
                    <span
                      className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getBadgeTone(c.risk_level)}`}
                    >
                      {c.risk_score}/100
                    </span>
                  </div>
                  <div className="mt-2.5 flex items-center justify-between text-[11px]">
                    <span
                      className={`rounded-full border px-2 py-0.5 font-medium ${getBadgeTone(c.status)}`}
                    >
                      {formatLabel(c.status)}
                    </span>
                    <span className="text-slate-400">{formatLabel(c.risk_level)} Risk</span>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="lg:col-span-8">
            {selectedDetail ? (
              <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-bold text-slate-900">
                        {selectedDetail.title}
                      </h3>
                      <span
                        className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${getBadgeTone(selectedDetail.risk_level)}`}
                      >
                        {selectedDetail.risk_score}/100 ({formatLabel(selectedDetail.risk_level)})
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {selectedDetail.vendor_name} &middot; {selectedDetail.contract_type} &middot;{' '}
                      {formatCurrency(selectedDetail.annual_value)}/yr &middot; Provider:{' '}
                      {selectedDetail.llm_provider_used}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRecompare()}
                    disabled={busy}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Re-run Comparison
                  </button>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3.5">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-indigo-700">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    AI Playbook Assessment
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-slate-700">
                    {selectedDetail.comparison_summary}
                  </p>
                </div>

                <div className="space-y-3">
                  {selectedDetail.findings.map((finding) => (
                    <div
                      key={finding.id}
                      className="rounded-lg border border-slate-200 p-3.5 text-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold text-slate-900">
                          {formatLabel(finding.clause_type)}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getBadgeTone(finding.status)}`}
                          >
                            {formatLabel(finding.status)}
                          </span>
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getBadgeTone(finding.severity)}`}
                          >
                            {formatLabel(finding.severity)}
                          </span>
                        </div>
                      </div>
                      <div className="mt-2 grid gap-2 sm:grid-cols-2">
                        <div className="rounded bg-slate-50 p-2">
                          <p className="text-[10px] font-semibold uppercase text-slate-400">
                            Vendor Draft
                          </p>
                          <p className="mt-0.5 text-slate-700">{finding.vendor_excerpt}</p>
                        </div>
                        <div className="rounded bg-indigo-50/50 p-2">
                          <p className="text-[10px] font-semibold uppercase text-indigo-600">
                            Playbook Standard
                          </p>
                          <p className="mt-0.5 text-slate-700">{finding.playbook_position}</p>
                        </div>
                      </div>
                      {finding.redline_suggestion && (
                        <p className="mt-2 text-[11px] font-medium text-slate-700">
                          <span className="font-semibold text-indigo-700">Recommended Redline:</span>{' '}
                          {finding.redline_suggestion}
                        </p>
                      )}
                    </div>
                  ))}
                </div>

                <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
                  <input
                    value={requestedBy}
                    onChange={(e) => setRequestedBy(e.target.value)}
                    placeholder="Requester name"
                    className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                  />
                  <input
                    value={approvalNotes}
                    onChange={(e) => setApprovalNotes(e.target.value)}
                    placeholder="Approval justification or redline waiver notes..."
                    className="min-w-[220px] flex-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => void handleRequestApproval()}
                    disabled={busy}
                    className="rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
                  >
                    Request Legal / Procurement Sign-Off
                  </button>
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-xs text-slate-500">
                Select a contract to inspect playbook diffs.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
