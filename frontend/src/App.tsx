import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  BarChart3,
  Building2,
  CalendarClock,
  FileText,
  KeyRound,
  LayoutDashboard,
  Receipt,
  ShieldCheck,
} from 'lucide-react';
import { getAuthToken, procurementApi, setAuthToken } from './api/client';
import { AuthModal } from './components/AuthModal';
import { BenchmarksView } from './components/BenchmarksView';
import { ContractsView } from './components/ContractsView';
import { GovernanceView } from './components/GovernanceView';
import { OverviewDashboard, type WorkspaceTab } from './components/OverviewDashboard';
import { PurchasingView } from './components/PurchasingView';
import { RenewalsView } from './components/RenewalsView';
import { VendorsView } from './components/VendorsView';
import type {
  ApprovalRequest,
  AuthUser,
  DashboardSummary,
  HealthStatus,
  Vendor,
} from './types/procurement';
import { formatLabel } from './utils/format';

const NAV_ITEMS: Array<{
  id: WorkspaceTab;
  label: string;
  icon: typeof LayoutDashboard;
}> = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'vendors', label: 'Vendors', icon: Building2 },
  { id: 'contracts', label: 'Contracts', icon: FileText },
  { id: 'benchmarks', label: 'Pricing Benchmarks', icon: BarChart3 },
  { id: 'purchasing', label: 'PO Validation', icon: Receipt },
  { id: 'renewals', label: 'Renewals', icon: CalendarClock },
  { id: 'governance', label: 'Approvals & Audit', icon: ShieldCheck },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('overview');
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [offline, setOffline] = useState(false);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [loading, setLoading] = useState(true);

  const refreshWorkspace = useCallback(async () => {
    try {
      const [summaryRes, vendorRes, approvalRes] = await Promise.all([
        procurementApi.getDashboardSummary(),
        procurementApi.listVendors(),
        procurementApi.listApprovals('pending'),
      ]);
      setSummary(summaryRes);
      setVendors(vendorRes);
      setApprovals(approvalRes);
    } catch {
      // Keep graceful offline fallback if domain endpoints are unreachable.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      setLoading(true);
      try {
        const response = await fetch('/api/v1/health');
        if (!response.ok) {
          if (!cancelled) {
            setOffline(true);
            setLoading(false);
          }
          return;
        }
        const payload = (await response.json()) as HealthStatus;
        if (!cancelled) {
          setHealth(payload);
          setOffline(false);
        }
        if (getAuthToken()) {
          try {
            const me = await procurementApi.getMe();
            if (!cancelled) setCurrentUser(me);
          } catch {
            setAuthToken(null);
          }
        }
        await refreshWorkspace();
      } catch {
        if (!cancelled) {
          setOffline(true);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [refreshWorkspace]);

  async function handleSeedDemo() {
    await procurementApi.triggerSeed();
    await refreshWorkspace();
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600">
              Autonomous Procurement &amp; Vendor Intelligence
            </p>
            <h1 className="mt-0.5 text-xl font-bold tracking-tight text-slate-900">
              AI Procurement &amp; Vendor Manager
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 text-xs font-medium">
            {health?.pii_redaction_enabled !== false && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-700">
                <ShieldCheck className="h-3.5 w-3.5" />
                Cloud PII Redaction On
              </span>
            )}
            <button
              type="button"
              onClick={() => setShowAuthModal(true)}
              className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-indigo-800 hover:bg-indigo-100"
            >
              <KeyRound className="h-3.5 w-3.5" />
              <span>
                {currentUser
                  ? `${currentUser.full_name} (${formatLabel(currentUser.role)})`
                  : 'Sign In (RBAC)'}
              </span>
            </button>
            <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3.5 py-1">
              <Activity
                className={`h-3.5 w-3.5 ${
                  health?.status === 'ok'
                    ? 'text-emerald-600'
                    : offline
                    ? 'text-amber-600'
                    : 'text-slate-400'
                }`}
              />
              <span>
                {health?.status === 'ok'
                  ? `API Healthy (${health.llm_provider})`
                  : offline
                  ? 'Offline Starter Preview'
                  : 'Checking API...'}
              </span>
            </div>
          </div>
        </div>

        <nav
          aria-label="Primary workspaces"
          className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-6"
        >
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = activeTab === item.id;
            const showBadge = item.id === 'governance' && approvals.length > 0;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveTab(item.id)}
                className={`inline-flex shrink-0 items-center gap-2 border-b-2 px-3.5 py-2.5 text-xs font-semibold transition ${
                  active
                    ? 'border-indigo-600 text-indigo-700'
                    : 'border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{item.label}</span>
                {showBadge && (
                  <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">
                    {approvals.length}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        {activeTab === 'overview' && (
          <OverviewDashboard
            summary={summary}
            approvals={approvals}
            loading={loading}
            onNavigate={setActiveTab}
            onSeedDemo={handleSeedDemo}
          />
        )}
        {activeTab === 'vendors' && (
          <VendorsView vendors={vendors} onDataChange={refreshWorkspace} />
        )}
        {activeTab === 'contracts' && (
          <ContractsView vendors={vendors} onDataChange={refreshWorkspace} />
        )}
        {activeTab === 'benchmarks' && (
          <BenchmarksView vendors={vendors} onDataChange={refreshWorkspace} />
        )}
        {activeTab === 'purchasing' && (
          <PurchasingView vendors={vendors} onDataChange={refreshWorkspace} />
        )}
        {activeTab === 'renewals' && (
          <RenewalsView vendors={vendors} onDataChange={refreshWorkspace} />
        )}
        {activeTab === 'governance' && (
          <GovernanceView currentUser={currentUser} onDataChange={refreshWorkspace} />
        )}
      </main>

      {showAuthModal && (
        <AuthModal
          currentUser={currentUser}
          onClose={() => setShowAuthModal(false)}
          onAuthenticated={(user) => {
            setCurrentUser(user);
            void refreshWorkspace();
          }}
        />
      )}
    </div>
  );
}
