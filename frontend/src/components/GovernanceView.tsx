import { useEffect, useState } from 'react';
import { Check, Download, LockKeyhole, ShieldCheck, X } from 'lucide-react';
import { procurementApi } from '../api/client';
import type {
  ApprovalRequest,
  AuditChainVerification,
  AuditLogEntry,
  AuthUser,
} from '../types/procurement';
import { formatCurrency, formatLabel, getBadgeTone } from '../utils/format';

interface GovernanceViewProps {
  currentUser: AuthUser | null;
  onDataChange: () => Promise<void>;
}

export function GovernanceView({ currentUser, onDataChange }: GovernanceViewProps) {
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [statusFilter, setStatusFilter] = useState<'pending' | 'approved' | 'rejected' | 'all'>(
    'pending'
  );
  const [reviewerName, setReviewerName] = useState('Arthur Gomez');
  const [decisionNotes, setDecisionNotes] = useState('');
  const [verification, setVerification] = useState<AuditChainVerification | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadGovernance(nextFilter = statusFilter) {
    try {
      const [approvalRows, auditRows] = await Promise.all([
        procurementApi.listApprovals(nextFilter === 'all' ? undefined : nextFilter),
        procurementApi.listAuditLogs(),
      ]);
      setApprovals(approvalRows);
      setAuditLogs(auditRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load governance records');
    }
  }

  useEffect(() => {
    void loadGovernance(statusFilter);
  }, [statusFilter]);

  const effectiveReviewer = currentUser?.full_name || reviewerName || 'Finance Reviewer';

  async function handleDecide(approvalId: string, decision: 'approved' | 'rejected') {
    setBusy(true);
    setError(null);
    setStatusMessage(null);
    try {
      const updated = await procurementApi.decideApproval(
        approvalId,
        decision,
        effectiveReviewer,
        decisionNotes || `${decision.toUpperCase()} via Governance Desk.`
      );
      setStatusMessage(`Recorded HITL ${updated.status} decision for "${updated.title}".`);
      setDecisionNotes('');
      await loadGovernance(statusFilter);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to record approval decision');
    } finally {
      setBusy(false);
    }
  }

  async function handleVerifyChain() {
    setBusy(true);
    setError(null);
    try {
      const result = await procurementApi.verifyAuditChain();
      setVerification(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Hash-chain verification failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">
          Human-in-the-Loop Approvals &amp; Immutable Audit Ledger
        </h2>
        <p className="text-xs text-slate-600">
          Explicit review gates for PO commitments, high-risk contracts, and outbound non-renewal
          notices backed by a SHA-256 hash-chained audit trail.{' '}
          {currentUser ? (
            <span className="font-semibold text-indigo-700">
              Active RBAC Identity: {currentUser.full_name} ({formatLabel(currentUser.role)}) —
              Separation of duties enforced.
            </span>
          ) : (
            <span className="text-slate-500">
              Separation of duties enforced (sign in via top bar to enforce role gates).
            </span>
          )}
        </p>
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

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
          <div className="flex flex-wrap items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-indigo-600" />
            <h3 className="text-sm font-semibold text-slate-900">Approval Queue</h3>
            <div className="ml-2 flex gap-1">
              {(['pending', 'approved', 'rejected', 'all'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setStatusFilter(tab)}
                  className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                    statusFilter === tab
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {formatLabel(tab)}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              aria-label="Reviewer Name"
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              placeholder="Reviewer Name"
              className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            />
            <input
              aria-label="Decision Notes"
              value={decisionNotes}
              onChange={(e) => setDecisionNotes(e.target.value)}
              placeholder="Reviewer notes..."
              className="w-56 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            />
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {approvals.length === 0 ? (
            <p className="py-4 text-center text-xs text-slate-500">
              No {statusFilter === 'all' ? '' : statusFilter} approval requests found.
            </p>
          ) : (
            approvals.map((item) => (
              <div
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 p-4"
              >
                <div className="max-w-2xl space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-bold text-slate-900">{item.title}</span>
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getBadgeTone(item.status)}`}
                    >
                      {formatLabel(item.status)}
                    </span>
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                      Role: {formatLabel(item.required_role)}
                    </span>
                    {item.amount_impact > 0 && (
                      <span className="text-[11px] font-semibold text-indigo-700">
                        Impact: {formatCurrency(item.amount_impact)}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-600">{item.summary}</p>
                  <p className="text-[11px] text-slate-400">
                    Requested by {item.requested_by}
                    {item.decided_by
                      ? ` · Decided by ${item.decided_by} (${item.decision_notes})`
                      : ''}
                  </p>
                </div>

                {item.status === 'pending' && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void handleDecide(item.id, 'approved')}
                      disabled={busy}
                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      <Check className="h-3.5 w-3.5" />
                      Approve
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDecide(item.id, 'rejected')}
                      disabled={busy}
                      className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50"
                    >
                      <X className="h-3.5 w-3.5" />
                      Reject
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-3.5">
          <div className="flex items-center gap-2">
            <LockKeyhole className="h-4 w-4 text-slate-700" />
            <h3 className="text-sm font-semibold text-slate-900">
              Immutable Audit Log ({auditLogs.length} recent entries)
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <a
              href={procurementApi.exportAuditLogsUrl('csv')}
              download
              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <Download className="h-3.5 w-3.5" />
              Export CSV
            </a>
            <a
              href={procurementApi.exportAuditLogsUrl('json')}
              download
              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <Download className="h-3.5 w-3.5" />
              Export Signed JSON
            </a>
            <button
              type="button"
              onClick={() => void handleVerifyChain()}
              disabled={busy}
              className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-800 hover:bg-indigo-100"
            >
              Verify Hash Chain Integrity
            </button>
          </div>
        </div>

        {verification && (
          <div
            className={`mx-5 mt-4 rounded-lg border px-4 py-2.5 text-xs font-medium ${
              verification.valid
                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                : 'border-rose-200 bg-rose-50 text-rose-800'
            }`}
          >
            {verification.valid
              ? `SHA-256 Hash Chain Verified: ${verification.total_entries} entries intact (head ${verification.latest_hash?.slice(0, 14) ?? 'genesis'}...).`
              : `Hash Chain Break Detected at sequence #${verification.broken_at_sequence}!`}
          </div>
        )}

        <div className="overflow-x-auto p-2">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-100 bg-slate-50 text-[11px] uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Actor</th>
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2">Summary</th>
                <th className="px-3 py-2">Entry Hash</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {auditLogs.map((log) => (
                <tr key={log.id}>
                  <td className="px-3 py-2 font-mono text-[11px] text-slate-500">
                    #{log.sequence_num}
                  </td>
                  <td className="px-3 py-2 font-medium text-slate-800">{log.actor}</td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-700">
                      {log.action}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-700">{log.summary}</td>
                  <td className="px-3 py-2 font-mono text-[10px] text-slate-400">
                    {log.entry_hash.slice(0, 14)}...
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
