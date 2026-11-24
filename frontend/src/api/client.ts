import type {
  ApprovalRequest,
  AuditChainVerification,
  AuditLogEntry,
  BenchmarkSummary,
  BudgetAccount,
  Contract,
  ContractDetail,
  ContractPairComparison,
  DashboardSummary,
  HealthStatus,
  PlaybookRule,
  POLineItem,
  PricingBenchmark,
  PurchaseOrder,
  QuoteAnalysisResult,
  RenewalBriefResponse,
  RenewalItem,
  Vendor,
  VendorQuote,
} from '../types/procurement';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const errBody = (await response.json()) as { detail?: string };
      if (errBody?.detail) {
        message = errBody.detail;
      }
    } catch {
      // Fall back to status message when body is non-JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const procurementApi = {
  getHealth: () => apiFetch<HealthStatus>('/api/v1/health'),
  getDashboardSummary: () => apiFetch<DashboardSummary>('/api/v1/dashboard/summary'),
  triggerSeed: () => apiFetch<Record<string, number>>('/api/v1/seed', { method: 'POST' }),

  listVendors: () => apiFetch<Vendor[]>('/api/v1/vendors'),
  createVendor: (payload: Partial<Vendor>) =>
    apiFetch<Vendor>('/api/v1/vendors', { method: 'POST', body: JSON.stringify(payload) }),

  listPlaybooks: () => apiFetch<PlaybookRule[]>('/api/v1/contracts/playbooks'),
  listContracts: () => apiFetch<Contract[]>('/api/v1/contracts'),
  getContract: (id: string) => apiFetch<ContractDetail>(`/api/v1/contracts/${id}`),
  createContract: (payload: {
    vendor_id: string;
    title: string;
    contract_type: string;
    annual_value: number;
    raw_text: string;
    auto_compare?: boolean;
  }) =>
    apiFetch<ContractDetail>('/api/v1/contracts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  recompareContract: (id: string) =>
    apiFetch<ContractDetail>(`/api/v1/contracts/${id}/compare`, { method: 'POST' }),
  compareContractPair: (leftId: string, rightId: string) =>
    apiFetch<ContractPairComparison>('/api/v1/contracts/compare-pair', {
      method: 'POST',
      body: JSON.stringify({ left_contract_id: leftId, right_contract_id: rightId }),
    }),
  requestContractApproval: (id: string, requestedBy: string, notes: string) =>
    apiFetch<{ approval_id: string; status: string; required_role: string }>(
      `/api/v1/contracts/${id}/request-approval`,
      {
        method: 'POST',
        body: JSON.stringify({ requested_by: requestedBy, notes }),
      }
    ),

  listBenchmarks: () => apiFetch<PricingBenchmark[]>('/api/v1/benchmarks'),
  getBenchmarkSummary: () => apiFetch<BenchmarkSummary[]>('/api/v1/benchmarks/summary'),
  createBenchmark: (payload: {
    vendor_id?: string | null;
    sku_code: string;
    sku_name: string;
    category: string;
    unit_type: string;
    volume_tier: string;
    quoted_unit_price: number;
    annual_uplift_pct: number;
    discount_pct: number;
    source: string;
    effective_year: number;
    notes?: string;
  }) =>
    apiFetch<PricingBenchmark>('/api/v1/benchmarks', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  analyzeQuote: (payload: {
    sku_code?: string;
    category: string;
    unit_type: string;
    volume_tier?: string;
    quantity: number;
    proposed_unit_price: number;
    proposed_uplift_pct: number;
  }) =>
    apiFetch<QuoteAnalysisResult>('/api/v1/benchmarks/analyze', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listBudgets: () => apiFetch<BudgetAccount[]>('/api/v1/purchasing/budgets'),
  listQuotes: () => apiFetch<VendorQuote[]>('/api/v1/purchasing/quotes'),
  listPurchaseOrders: () => apiFetch<PurchaseOrder[]>('/api/v1/purchasing/orders'),
  createPurchaseOrder: (payload: {
    po_number: string;
    vendor_id: string;
    quote_id?: string | null;
    cost_center_code: string;
    requester_name: string;
    line_items: POLineItem[];
  }) =>
    apiFetch<PurchaseOrder>('/api/v1/purchasing/orders', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  revalidatePurchaseOrder: (id: string) =>
    apiFetch<PurchaseOrder>(`/api/v1/purchasing/orders/${id}/validate`, { method: 'POST' }),
  submitPurchaseOrder: (id: string, requestedBy: string, justification: string) =>
    apiFetch<{ approval_id: string; status: string; required_role: string }>(
      `/api/v1/purchasing/orders/${id}/submit`,
      {
        method: 'POST',
        body: JSON.stringify({
          requested_by: requestedBy,
          override_warnings: true,
          justification,
        }),
      }
    ),

  listRenewals: () => apiFetch<RenewalItem[]>('/api/v1/renewals'),
  createRenewal: (payload: {
    vendor_id: string;
    contract_id?: string | null;
    contract_title: string;
    renewal_date: string;
    notice_period_days: number;
    auto_renew: boolean;
    current_annual_value: number;
    proposed_uplift_pct: number;
    owner_name: string;
  }) =>
    apiFetch<RenewalItem>('/api/v1/renewals', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  generateRenewalBrief: (id: string) =>
    apiFetch<RenewalBriefResponse>(`/api/v1/renewals/${id}/generate-brief`, {
      method: 'POST',
    }),
  requestRenewalAction: (
    id: string,
    actionType: 'send_non_renewal_notice' | 'approve_renewal_terms' | 'request_renegotiation',
    requestedBy: string,
    notes: string
  ) =>
    apiFetch<{ approval_id: string; status: string; required_role: string }>(
      `/api/v1/renewals/${id}/request-action`,
      {
        method: 'POST',
        body: JSON.stringify({
          action_type: actionType,
          requested_by: requestedBy,
          notes,
        }),
      }
    ),

  listApprovals: (status?: string) =>
    apiFetch<ApprovalRequest[]>(
      status ? `/api/v1/governance/approvals?status=${encodeURIComponent(status)}` : '/api/v1/governance/approvals'
    ),
  decideApproval: (
    id: string,
    decision: 'approved' | 'rejected',
    decidedBy: string,
    decisionNotes: string
  ) =>
    apiFetch<ApprovalRequest>(`/api/v1/governance/approvals/${id}/decide`, {
      method: 'POST',
      body: JSON.stringify({
        decision,
        decided_by: decidedBy,
        decision_notes: decisionNotes,
      }),
    }),
  listAuditLogs: () => apiFetch<AuditLogEntry[]>('/api/v1/governance/audit-logs?limit=100'),
  verifyAuditChain: () =>
    apiFetch<AuditChainVerification>('/api/v1/governance/audit-logs/verify'),
};
