export interface HealthStatus {
  status: string;
  service: string;
  app_name: string;
  version: string;
  environment: string;
  llm_provider: string;
  database?: string;
  pii_redaction_enabled?: boolean;
}

export interface Vendor {
  id: string;
  name: string;
  category: string;
  tier: 'strategic' | 'preferred' | 'standard' | string;
  status: 'active' | 'under_review' | 'offboarding' | string;
  primary_contact_name: string;
  primary_contact_email: string;
  annual_spend: number;
  risk_score: number;
  payment_terms_days: number;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface PlaybookRule {
  id: string;
  name: string;
  clause_type: string;
  preferred_position: string;
  fallback_position: string;
  max_acceptable_value: number | null;
  severity: 'critical' | 'high' | 'medium' | 'low' | string;
  guidance: string;
  is_active: boolean;
  created_at: string;
}

export interface ContractClauseFinding {
  id: string;
  contract_id: string;
  clause_type: string;
  status: 'compliant' | 'favorable' | 'deviation' | 'missing' | string;
  severity: 'critical' | 'high' | 'medium' | 'low' | string;
  vendor_excerpt: string;
  playbook_position: string;
  redline_suggestion: string;
  deviation_score: number;
  created_at: string;
}

export interface Contract {
  id: string;
  vendor_id: string;
  vendor_name: string;
  title: string;
  contract_type: 'MSA' | 'DPA' | 'Order Form' | 'SOW' | string;
  effective_date: string | null;
  expiration_date: string | null;
  annual_value: number;
  raw_text: string;
  status: 'draft' | 'in_review' | 'redline_required' | 'approved' | string;
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical' | string;
  comparison_summary: string;
  llm_provider_used: string;
  pii_redacted: boolean;
  last_compared_at: string | null;
  created_at: string;
}

export interface ContractDetail extends Contract {
  findings: ContractClauseFinding[];
}

export interface ClausePairDiffItem {
  clause_type: string;
  left_status: string;
  left_severity: string;
  left_excerpt: string;
  right_status: string;
  right_severity: string;
  right_excerpt: string;
  delta_summary: string;
}

export interface ContractPairComparison {
  left_contract: Contract;
  right_contract: Contract;
  clause_diffs: ClausePairDiffItem[];
  recommendation: string;
}

export interface PricingBenchmark {
  id: string;
  vendor_id: string | null;
  vendor_name: string;
  sku_code: string;
  sku_name: string;
  category: string;
  unit_type: string;
  volume_tier: string;
  quoted_unit_price: number;
  currency: string;
  annual_uplift_pct: number;
  discount_pct: number;
  source: string;
  effective_year: number;
  notes: string;
  created_at: string;
}

export interface BenchmarkSummary {
  sku_code: string;
  sku_name: string;
  category: string;
  unit_type: string;
  sample_size: number;
  min_price: number;
  p25_price: number;
  median_price: number;
  p75_price: number;
  max_price: number;
  avg_uplift_pct: number;
  avg_discount_pct: number;
}

export interface QuoteAnalysisResult {
  matched_by: string;
  sample_size: number;
  min_price: number;
  p25_price: number;
  median_price: number;
  p75_price: number;
  max_price: number;
  avg_uplift_pct: number;
  avg_discount_pct: number;
  proposed_unit_price: number;
  variance_vs_median_pct: number;
  percentile_rank: number;
  rating: 'below_market' | 'competitive' | 'above_market' | 'outlier_high' | string;
  estimated_annual_spend: number;
  target_unit_price: number;
  target_annual_spend: number;
  potential_annual_savings: number;
  uplift_assessment: string;
  negotiation_recommendation: string;
}

export interface BudgetAccount {
  id: string;
  cost_center_code: string;
  department: string;
  fiscal_year: number;
  annual_budget: number;
  committed_amount: number;
  remaining_budget: number;
  owner_name: string;
  created_at: string;
}

export interface POLineItem {
  sku_code: string;
  description: string;
  quantity: number;
  unit_price: number;
  line_total: number;
}

export interface ValidationIssue {
  code: string;
  severity: 'pass' | 'warning' | 'fail' | string;
  message: string;
  field: string;
}

export interface VendorQuote {
  id: string;
  vendor_id: string;
  vendor_name: string;
  quote_number: string;
  currency: string;
  valid_until: string;
  total_amount: number;
  line_items_json: POLineItem[];
  created_at: string;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  vendor_id: string;
  vendor_name: string;
  quote_id: string | null;
  cost_center_code: string;
  requester_name: string;
  currency: string;
  total_amount: number;
  line_items_json: POLineItem[];
  status: 'draft' | 'validated' | 'pending_approval' | 'approved' | 'rejected' | 'blocked' | string;
  validation_status: 'pass' | 'warning' | 'fail' | string;
  validation_issues_json: ValidationIssue[];
  required_approver_role: string;
  approval_request_id: string | null;
  ai_risk_summary: string;
  created_at: string;
  updated_at: string;
}

export interface RenewalItem {
  id: string;
  vendor_id: string;
  vendor_name: string;
  contract_id: string | null;
  contract_title: string;
  renewal_date: string;
  notice_period_days: number;
  notice_deadline: string;
  days_to_notice_deadline: number;
  urgency: 'overdue' | 'critical' | 'upcoming' | 'healthy' | string;
  auto_renew: boolean;
  current_annual_value: number;
  proposed_uplift_pct: number;
  projected_renewal_value: number;
  owner_name: string;
  decision_status: string;
  brief_markdown: string;
  brief_data_json: Record<string, unknown>;
  brief_generated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RenewalBriefResponse {
  renewal: RenewalItem;
  projected_value: number;
  target_value: number;
  estimated_annual_savings: number;
  three_year_savings: number;
  leverage_points: string[];
  clause_redlines: string[];
  recommended_timeline: string[];
  draft_notice_email: string;
  brief_markdown: string;
}

export interface ApprovalRequest {
  id: string;
  entity_type: string;
  entity_id: string;
  action_type: string;
  title: string;
  summary: string;
  required_role: string;
  amount_impact: number;
  status: 'pending' | 'approved' | 'rejected' | string;
  requested_by: string;
  decided_by: string | null;
  decision_notes: string;
  payload_json: Record<string, unknown>;
  created_at: string;
  decided_at: string | null;
}

export interface AuditLogEntry {
  id: string;
  sequence_num: number;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string;
  summary: string;
  metadata_json: Record<string, unknown>;
  prev_hash: string;
  entry_hash: string;
  created_at: string;
}

export interface AuditChainVerification {
  valid: boolean;
  total_entries: number;
  latest_hash: string | null;
  broken_at_sequence: number | null;
}

export interface CategorySpendItem {
  category: string;
  annual_spend: number;
  vendor_count: number;
}

export interface AuditActivitySummary {
  sequence_num: number;
  actor: string;
  action: string;
  entity_type: string;
  summary: string;
  entry_hash: string;
  created_at: string;
}

export interface DashboardSummary {
  total_vendors: number;
  total_annual_spend: number;
  active_contracts: number;
  high_risk_contracts: number;
  avg_contract_risk_score: number;
  benchmarks_count: number;
  pending_approvals_count: number;
  open_pos_count: number;
  blocked_pos_count: number;
  urgent_renewals_count: number;
  estimated_savings_opportunity: number;
  spend_by_category: CategorySpendItem[];
  urgent_renewals: RenewalItem[];
  recent_audit_logs: AuditActivitySummary[];
}
