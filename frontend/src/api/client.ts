import type {
  ApprovalRequest,
  AuditChainVerification,
  AuditLogEntry,
  AuthTokenResponse,
  AuthUser,
  BenchmarkSummary,
  BudgetAccount,
  ClauseSearchHit,
  Contract,
  ContractDetail,
  ContractPairComparison,
  CsvImportResult,
  DashboardSummary,
  HealthStatus,
  PlaybookRule,
  POLineItem,
  PricingBenchmark,
  PurchaseOrder,
  QuoteAnalysisResult,
  RenewalAlertDispatch,
  RenewalBriefResponse,
  RenewalItem,
  Vendor,
  VendorQuote,
} from '../types/procurement';

const TOKEN_STORAGE_KEY = 'ai_procurement_auth_token';
let memoryToken: string | null = null;

export function getAuthToken(): string | null {
  if (memoryToken) return memoryToken;
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null): void {
  memoryToken = token;
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // Ignore storage errors in restricted environments.
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = typeof FormData !== 'undefined' && init?.body instanceof FormData;
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (!isFormData) {
    headers['Content-Type'] = 'application/json';
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(path, {
    ...init,
    headers: {
      ...headers,
      ...(init?.headers as Record<string, string> | undefined),
    },
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

  login: (email: string, password: string) =>
    apiFetch<AuthTokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  register: (payload: { email: string; full_name: string; password: string; role: string }) =>
    apiFetch<AuthTokenResponse>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getMe: () => apiFetch<AuthUser>('/api/v1/auth/me'),
  listUsers: () => apiFetch<AuthUser[]>('/api/v1/auth/users'),

  listVendors: () => apiFetch<Vendor[]>('/api/v1/vendors'),
  createVendor: (payload: Partial<Vendor>) =>
    apiFetch<Vendor>('/api/v1/vendors', { method: 'POST', body: JSON.stringify(payload) }),
  updateVendor: (id: string, payload: Partial<Vendor>) =>
    apiFetch<Vendor>(`/api/v1/vendors/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  listPlaybooks: () => apiFetch<PlaybookRule[]>('/api/v1/contracts/playbooks'),
  createPlaybookRule: (payload: {
    name: string;
    clause_type: string;
    preferred_position: string;
    fallback_position?: string;
    max_acceptable_value?: number | null;
    severity: string;
    guidance?: string;
  }) =>
    apiFetch<PlaybookRule>('/api/v1/contracts/playbooks', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
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
  uploadContract: (payload: {
    vendor_id: string;
    title: string;
    contract_type: string;
    annual_value: number;
    file: File;
  }) => {
    const form = new FormData();
    form.append('vendor_id', payload.vendor_id);
    form.append('title', payload.title);
    form.append('contract_type', payload.contract_type);
    form.append('annual_value', String(payload.annual_value));
    form.append('auto_compare', 'true');
    form.append('file', payload.file);
    return apiFetch<ContractDetail>('/api/v1/contracts/upload', {
      method: 'POST',
      body: form,
    });
  },
  searchContractClauses: (query: string, clauseType?: string) =>
    apiFetch<ClauseSearchHit[]>('/api/v1/contracts/search', {
      method: 'POST',
      body: JSON.stringify({
        query,
        clause_type: clauseType || undefined,
        top_k: 8,
      }),
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
  importBenchmarksCsv: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiFetch<CsvImportResult>('/api/v1/benchmarks/import-csv', {
      method: 'POST',
      body: form,
    });
  },
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
  createBudget: (payload: {
    cost_center_code: string;
    department: string;
    fiscal_year: number;
    annual_budget: number;
    committed_amount: number;
    owner_name: string;
  }) =>
    apiFetch<BudgetAccount>('/api/v1/purchasing/budgets', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  importBudgetsCsv: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiFetch<CsvImportResult>('/api/v1/purchasing/budgets/import-csv', {
      method: 'POST',
      body: form,
    });
  },
  listQuotes: () => apiFetch<VendorQuote[]>('/api/v1/purchasing/quotes'),
  createQuote: (payload: {
    vendor_id: string;
    quote_number: string;
    valid_until: string;
    line_items: POLineItem[];
  }) =>
    apiFetch<VendorQuote>('/api/v1/purchasing/quotes', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
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
  listRenewalAlerts: () => apiFetch<RenewalAlertDispatch[]>('/api/v1/renewals/alerts'),
  runRenewalAlertSweep: () =>
    apiFetch<{
      checked_count: number;
      dispatched_count: number;
      dispatches: RenewalAlertDispatch[];
    }>('/api/v1/renewals/alerts/run', { method: 'POST' }),
  exportRenewalBriefUrl: (id: string) => `/api/v1/renewals/${id}/export`,
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
      status
        ? `/api/v1/governance/approvals?status=${encodeURIComponent(status)}`
        : '/api/v1/governance/approvals'
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
  exportAuditLogsUrl: (exportFormat: 'csv' | 'json') =>
    `/api/v1/governance/audit-logs/export?export_format=${exportFormat}`,
};
