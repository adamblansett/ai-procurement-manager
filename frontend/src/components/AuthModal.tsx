import { type FormEvent, useState } from 'react';
import { KeyRound, LogOut, ShieldCheck, X } from 'lucide-react';
import { procurementApi, setAuthToken } from '../api/client';
import type { AuthUser } from '../types/procurement';
import { formatLabel } from '../utils/format';

interface AuthModalProps {
  currentUser: AuthUser | null;
  onClose: () => void;
  onAuthenticated: (user: AuthUser | null) => void;
}

const DEMO_PERSONAS: Array<{ email: string; label: string; role: string }> = [
  { email: 'finance.director@procurement.local', label: 'Arthur Gomez', role: 'finance_director' },
  { email: 'vp.finance@procurement.local', label: 'Evelyn Shaw', role: 'vp_finance' },
  { email: 'legal.counsel@procurement.local', label: 'Diana Morales', role: 'legal_counsel' },
  { email: 'procurement.mgr@procurement.local', label: 'Samira Chen', role: 'procurement_manager' },
  { email: 'analyst@procurement.local', label: 'Nadia Patel', role: 'analyst' },
  { email: 'admin@procurement.local', label: 'Morgan Blake', role: 'admin' },
];

export function AuthModal({ currentUser, onClose, onAuthenticated }: AuthModalProps) {
  const [email, setEmail] = useState('finance.director@procurement.local');
  const [password, setPassword] = useState('ProcurementDemo2026!');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signInWith(targetEmail: string, targetPassword: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await procurementApi.login(targetEmail, targetPassword);
      setAuthToken(res.access_token);
      onAuthenticated(res.user);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    await signInWith(email, password);
  }

  function handleLogout() {
    setAuthToken(null);
    onAuthenticated(null);
    onClose();
  }

  return (
    <div
      role="dialog"
      aria-label="RBAC Authentication"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
    >
      <div className="w-full max-w-md space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-indigo-600" />
            <h3 className="text-sm font-bold text-slate-900">Sign In &amp; RBAC Identity</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close sign in"
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {currentUser && (
          <div className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs">
            <div>
              <p className="font-semibold text-emerald-950">{currentUser.full_name}</p>
              <p className="text-[11px] text-emerald-800">
                Role: {formatLabel(currentUser.role)} ({currentUser.email})
              </p>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="inline-flex items-center gap-1 rounded border border-emerald-300 bg-white px-2.5 py-1 text-[11px] font-semibold text-emerald-900 hover:bg-emerald-100"
            >
              <LogOut className="h-3 w-3" />
              Sign Out
            </button>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
            {error}
          </div>
        )}

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3">
          <label className="block text-xs">
            <span className="font-medium text-slate-700">Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs"
              required
            />
          </label>
          <label className="block text-xs">
            <span className="font-medium text-slate-700">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs"
              required
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? 'Authenticating...' : 'Sign In with Password'}
          </button>
        </form>

        <div className="border-t border-slate-100 pt-3">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500">
            <ShieldCheck className="h-3.5 w-3.5 text-indigo-600" />
            Quick Demo Role Switch (dev/demo users)
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {DEMO_PERSONAS.map((p) => (
              <button
                key={p.email}
                type="button"
                disabled={busy}
                onClick={() => void signInWith(p.email, 'ProcurementDemo2026!')}
                className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-left text-[11px] hover:border-indigo-300 hover:bg-indigo-50/40"
              >
                <div className="font-semibold text-slate-900">{p.label}</div>
                <div className="text-[10px] text-slate-500">{formatLabel(p.role)}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
