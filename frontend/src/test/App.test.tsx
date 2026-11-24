import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

const MOCK_VENDORS = [
  {
    id: 'v-1',
    name: 'Meridian RevOps CRM',
    category: 'SaaS Applications',
    tier: 'preferred',
    status: 'under_review',
    primary_contact_name: 'Marcus Sterling',
    primary_contact_email: 'm@meridian.example',
    annual_spend: 144000,
    risk_score: 64,
    payment_terms_days: 15,
    notes: '',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
  },
];

const MOCK_CONTRACTS = [
  {
    id: 'c-1',
    vendor_id: 'v-1',
    vendor_name: 'Meridian RevOps CRM',
    title: 'Meridian RevOps MSA',
    contract_type: 'MSA',
    effective_date: '2026-01-01',
    expiration_date: '2027-01-01',
    annual_value: 144000,
    raw_text: 'Auto-renews unless 90 days notice.',
    status: 'redline_required',
    risk_score: 76,
    risk_level: 'critical',
    comparison_summary: 'Key deviations detected in auto_renewal and price_uplift.',
    llm_provider_used: 'mock',
    pii_redacted: true,
    last_compared_at: '2026-11-24T12:00:00Z',
    created_at: '2026-11-24T12:00:00Z',
  },
];

const MOCK_CONTRACT_DETAIL = {
  ...MOCK_CONTRACTS[0],
  findings: [
    {
      id: 'f-1',
      contract_id: 'c-1',
      clause_type: 'price_uplift',
      status: 'deviation',
      severity: 'critical',
      vendor_excerpt: 'Fees increase 9% annually.',
      playbook_position: 'Max 5% annual uplift.',
      redline_suggestion: 'Cap annual price uplift from 9.0% down to <= 5.0%.',
      deviation_score: 78,
      created_at: '2026-11-24T12:00:00Z',
    },
  ],
};

const MOCK_RENEWAL = {
  id: 'r-1',
  vendor_id: 'v-1',
  vendor_name: 'Meridian RevOps CRM',
  contract_id: 'c-1',
  contract_title: 'Meridian RevOps Enterprise License',
  renewal_date: '2027-02-04',
  notice_period_days: 60,
  notice_deadline: '2026-12-06',
  days_to_notice_deadline: 12,
  urgency: 'critical',
  auto_renew: true,
  current_annual_value: 144000,
  proposed_uplift_pct: 9.0,
  projected_renewal_value: 156960,
  owner_name: 'Samira Chen',
  decision_status: 'monitoring',
  brief_markdown: '',
  brief_data_json: {},
  brief_generated_at: null,
  created_at: '2026-11-24T12:00:00Z',
  updated_at: '2026-11-24T12:00:00Z',
};

const MOCK_APPROVALS = [
  {
    id: 'a-1',
    entity_type: 'purchase_order',
    entity_id: 'po-1',
    action_type: 'approve_po',
    title: 'PO Approval: PO-2026-1002 (Vanguard)',
    summary: 'Approve Q4 security license expansion.',
    required_role: 'finance_director',
    amount_impact: 62500,
    status: 'pending',
    requested_by: 'Nadia Patel',
    decided_by: null,
    decision_notes: '',
    payload_json: {},
    created_at: '2026-11-24T12:00:00Z',
    decided_at: null,
  },
];

function createStubFetch() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    const method = (init?.method || 'GET').toUpperCase();

    const jsonResponse = (data: unknown) =>
      ({
        ok: true,
        status: 200,
        json: async () => data,
      }) as Response;

    if (url === '/api/v1/health') {
      return jsonResponse({
        status: 'ok',
        service: 'ai-procurement-manager',
        app_name: 'AI Procurement & Vendor Manager',
        version: '0.1.0',
        environment: 'test',
        llm_provider: 'mock',
        database: 'ok',
        pii_redaction_enabled: true,
      });
    }
    if (url === '/api/v1/dashboard/summary') {
      return jsonResponse({
        total_vendors: 5,
        total_annual_spend: 927000,
        active_contracts: 3,
        high_risk_contracts: 1,
        avg_contract_risk_score: 36.7,
        benchmarks_count: 12,
        pending_approvals_count: 1,
        open_pos_count: 1,
        blocked_pos_count: 1,
        urgent_renewals_count: 3,
        estimated_savings_opportunity: 24480,
        spend_by_category: [{ category: 'SaaS Applications', annual_spend: 144000, vendor_count: 1 }],
        urgent_renewals: [MOCK_RENEWAL],
        recent_audit_logs: [
          {
            sequence_num: 1,
            actor: 'seed-bootstrap',
            action: 'contract.compared',
            entity_type: 'contract',
            summary: 'Compared Meridian RevOps MSA',
            entry_hash: 'abcdef1234567890abcdef1234567890',
            created_at: '2026-11-24T12:00:00Z',
          },
        ],
      });
    }
    if (url === '/api/v1/vendors') return jsonResponse(MOCK_VENDORS);
    if (url === '/api/v1/contracts') return jsonResponse(MOCK_CONTRACTS);
    if (url === '/api/v1/contracts/playbooks') return jsonResponse([]);
    if (url === '/api/v1/contracts/c-1') return jsonResponse(MOCK_CONTRACT_DETAIL);

    if (url === '/api/v1/benchmarks') return jsonResponse([]);
    if (url === '/api/v1/benchmarks/summary') {
      return jsonResponse([
        {
          sku_code: 'CRM-ENT-SEAT',
          sku_name: 'Enterprise Revenue CRM Seat',
          category: 'SaaS Applications',
          unit_type: 'seat/month',
          sample_size: 3,
          min_price: 112,
          p25_price: 118.5,
          median_price: 125,
          p75_price: 132.5,
          max_price: 140,
          avg_uplift_pct: 3.17,
          avg_discount_pct: 18,
        },
      ]);
    }
    if (url === '/api/v1/benchmarks/analyze' && method === 'POST') {
      return jsonResponse({
        matched_by: 'sku_code',
        sample_size: 3,
        min_price: 112,
        p25_price: 118.5,
        median_price: 125,
        p75_price: 132.5,
        max_price: 140,
        avg_uplift_pct: 3.17,
        avg_discount_pct: 18,
        proposed_unit_price: 165,
        variance_vs_median_pct: 32.0,
        percentile_rank: 100,
        rating: 'outlier_high',
        estimated_annual_spend: 297000,
        target_unit_price: 118.5,
        target_annual_spend: 213300,
        potential_annual_savings: 83700,
        uplift_assessment: 'Proposed 8.5% uplift exceeds the 5.0% policy cap.',
        negotiation_recommendation: 'Counter at P25 ($118.50) to save $83,700/yr.',
      });
    }

    if (url === '/api/v1/purchasing/budgets') {
      return jsonResponse([
        {
          id: 'b-1',
          cost_center_code: 'CC-REV-310',
          department: 'Revenue Operations',
          fiscal_year: 2026,
          annual_budget: 210000,
          committed_amount: 192000,
          remaining_budget: 18000,
          owner_name: 'Samira Chen',
          created_at: '2026-11-24T12:00:00Z',
        },
      ]);
    }
    if (url === '/api/v1/purchasing/quotes') return jsonResponse([]);
    if (url === '/api/v1/purchasing/orders') {
      return jsonResponse([
        {
          id: 'po-blocked',
          po_number: 'PO-2026-1003',
          vendor_id: 'v-1',
          vendor_name: 'Meridian RevOps CRM',
          quote_id: 'q-1',
          cost_center_code: 'CC-REV-310',
          requester_name: 'Samira Chen',
          currency: 'USD',
          total_amount: 39000,
          line_items_json: [
            {
              sku_code: 'CRM-ENT-SEAT',
              description: 'CRM Seats',
              quantity: 200,
              unit_price: 195,
              line_total: 39000,
            },
          ],
          status: 'blocked',
          validation_status: 'fail',
          validation_issues_json: [
            {
              code: 'PRICE_OVERCHARGE',
              severity: 'fail',
              message: "SKU 'CRM-ENT-SEAT' unit price $195.00 exceeds quoted rate $145.00.",
              field: 'line_items',
            },
          ],
          required_approver_role: 'finance_director',
          approval_request_id: null,
          ai_risk_summary: 'PO-2026-1003 failed quote price and budget checks.',
          created_at: '2026-11-24T12:00:00Z',
          updated_at: '2026-11-24T12:00:00Z',
        },
      ]);
    }

    if (url === '/api/v1/renewals') return jsonResponse([MOCK_RENEWAL]);
    if (url === '/api/v1/renewals/r-1/generate-brief' && method === 'POST') {
      return jsonResponse({
        renewal: { ...MOCK_RENEWAL, decision_status: 'renegotiating' },
        projected_value: 156960,
        target_value: 132480,
        estimated_annual_savings: 24480,
        three_year_savings: 73440,
        leverage_points: ['Proposed 9.0% uplift exceeds 5.0% policy ceiling.'],
        clause_redlines: ['Cap annual price uplift at <= 5.0%.'],
        recommended_timeline: ['T-15: Serve protective notice.'],
        draft_notice_email: 'Subject: Protective Non-Renewal Notice',
        brief_markdown: '## Renegotiation Dossier',
      });
    }

    if (url.startsWith('/api/v1/governance/approvals') && method === 'GET') {
      return jsonResponse(MOCK_APPROVALS);
    }
    if (url === '/api/v1/governance/approvals/a-1/decide' && method === 'POST') {
      return jsonResponse({ ...MOCK_APPROVALS[0], status: 'approved', decided_by: 'Arthur Gomez' });
    }
    if (url.startsWith('/api/v1/governance/audit-logs?')) {
      return jsonResponse([
        {
          id: 'log-1',
          sequence_num: 1,
          actor: 'Arthur Gomez',
          action: 'approval.approved',
          entity_type: 'purchase_order',
          entity_id: 'po-1',
          summary: 'APPROVED PO-2026-1002',
          metadata_json: {},
          prev_hash: '0000',
          entry_hash: 'deadbeef1234567890',
          created_at: '2026-11-24T12:00:00Z',
        },
      ]);
    }
    if (url === '/api/v1/governance/audit-logs/verify') {
      return jsonResponse({
        valid: true,
        total_entries: 12,
        latest_hash: 'deadbeef1234567890',
        broken_at_sequence: null,
      });
    }

    return jsonResponse({});
  });
}

describe('AI Procurement & Vendor Manager workspace', () => {
  let fetchStub: ReturnType<typeof createStubFetch>;

  beforeEach(() => {
    fetchStub = createStubFetch();
    vi.stubGlobal('fetch', fetchStub);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders live API health status and overview dashboard KPIs', async () => {
    render(<App />);

    expect(
      screen.getByRole('heading', { name: 'AI Procurement & Vendor Manager' })
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/API Healthy \(mock\)/i)).toBeInTheDocument();
    });
    expect(screen.getByText('$927,000')).toBeInTheDocument();
    expect(screen.getByText('$24,480')).toBeInTheDocument();
    expect(fetchStub).toHaveBeenCalledWith('/api/v1/health');
  });

  it('navigates across Contracts, Benchmarks, PO Validation, Renewals, and Governance', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/API Healthy \(mock\)/i)).toBeInTheDocument();
    });

    // Contracts view
    fireEvent.click(screen.getByRole('button', { name: 'Contracts' }));
    await waitFor(() => {
      expect(screen.getByText('Cap annual price uplift from 9.0% down to <= 5.0%.')).toBeInTheDocument();
    });

    // Pricing Benchmarks view + Quote Analysis
    fireEvent.click(screen.getByRole('button', { name: 'Pricing Benchmarks' }));
    await waitFor(() => {
      expect(screen.getByText('Quote Benchmark Analyzer')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Analyze Quote vs Market' }));
    await waitFor(() => {
      expect(screen.getByText('$83,700')).toBeInTheDocument();
    });

    // PO Validation view
    fireEvent.click(screen.getByRole('button', { name: 'PO Validation' }));
    await waitFor(() => {
      expect(screen.getByText(/PRICE_OVERCHARGE/i)).toBeInTheDocument();
    });

    // Renewals view + Brief Generation
    fireEvent.click(screen.getByRole('button', { name: 'Renewals' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Generate AI Renegotiation Brief/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Generate AI Renegotiation Brief/i }));
    await waitFor(() => {
      expect(screen.getByText(/Subject: Protective Non-Renewal Notice/i)).toBeInTheDocument();
    });

    // Governance view + HITL Approval + Chain Verify
    fireEvent.click(screen.getByRole('button', { name: /Approvals & Audit/i }));
    await waitFor(() => {
      expect(screen.getByText('PO Approval: PO-2026-1002 (Vanguard)')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => {
      expect(screen.getByText(/Recorded HITL approved decision/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Verify Hash Chain Integrity' }));
    await waitFor(() => {
      expect(screen.getByText(/SHA-256 Hash Chain Verified: 12 entries intact/i)).toBeInTheDocument();
    });
  });
});
