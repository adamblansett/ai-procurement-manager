import { type FormEvent, useState } from 'react';
import { Building2, Edit3, PlusCircle } from 'lucide-react';
import { procurementApi } from '../api/client';
import type { Vendor } from '../types/procurement';
import { formatCurrency, formatLabel, getBadgeTone } from '../utils/format';

interface VendorsViewProps {
  vendors: Vendor[];
  onDataChange: () => Promise<void>;
}

export function VendorsView({ vendors, onDataChange }: VendorsViewProps) {
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<Vendor | null>(null);

  const [name, setName] = useState('');
  const [category, setCategory] = useState('SaaS Applications');
  const [tier, setTier] = useState('preferred');
  const [contactName, setContactName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [annualSpend, setAnnualSpend] = useState('50000');
  const [paymentTerms, setPaymentTerms] = useState('30');
  const [notes, setNotes] = useState('');

  const [editTier, setEditTier] = useState('preferred');
  const [editStatus, setEditStatus] = useState('active');
  const [editSpend, setEditSpend] = useState('0');
  const [editNotes, setEditNotes] = useState('');

  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function startEdit(v: Vendor) {
    setEditing(v);
    setEditTier(v.tier);
    setEditStatus(v.status);
    setEditSpend(String(v.annual_spend));
    setEditNotes(v.notes);
    setStatusMessage(null);
    setError(null);
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await procurementApi.createVendor({
        name,
        category,
        tier,
        status: 'active',
        primary_contact_name: contactName,
        primary_contact_email: contactEmail,
        annual_spend: Number(annualSpend) || 0,
        payment_terms_days: Number(paymentTerms) || 30,
        notes,
      });
      setShowAdd(false);
      setName('');
      setContactName('');
      setContactEmail('');
      setNotes('');
      setStatusMessage(`Added supplier '${created.name}'.`);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create vendor');
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await procurementApi.updateVendor(editing.id, {
        tier: editTier,
        status: editStatus,
        annual_spend: Number(editSpend) || 0,
        notes: editNotes,
      });
      setEditing(null);
      setStatusMessage(`Updated '${updated.name}' (${formatLabel(updated.status)}).`);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update vendor');
    } finally {
      setBusy(false);
    }
  }

  const categories = ['ALL', ...Array.from(new Set(vendors.map((v) => v.category)))];
  const visible =
    categoryFilter === 'ALL' ? vendors : vendors.filter((v) => v.category === categoryFilter);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Supplier Directory</h2>
          <p className="text-xs text-slate-600">
            Manage supplier tiers, commercial payment terms, spend envelopes, and review status.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAdd((prev) => !prev)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
        >
          <PlusCircle className="h-3.5 w-3.5" />
          Add Vendor
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

      {showAdd && (
        <form
          onSubmit={(e) => void handleCreate(e)}
          className="grid gap-3 rounded-xl border border-indigo-200 bg-white p-5 shadow-sm sm:grid-cols-4"
        >
          <label className="text-xs sm:col-span-2">
            <span className="font-medium text-slate-700">Vendor Name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Vertex Cloud Systems"
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Category</span>
            <input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Tier</span>
            <select
              value={tier}
              onChange={(e) => setTier(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            >
              <option value="strategic">Strategic</option>
              <option value="preferred">Preferred</option>
              <option value="standard">Standard</option>
            </select>
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Contact Name</span>
            <input
              value={contactName}
              onChange={(e) => setContactName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Contact Email</span>
            <input
              type="email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Annual Spend ($)</span>
            <input
              type="number"
              value={annualSpend}
              onChange={(e) => setAnnualSpend(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Payment Terms (Days)</span>
            <input
              type="number"
              value={paymentTerms}
              onChange={(e) => setPaymentTerms(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            />
          </label>
          <div className="flex justify-end gap-2 sm:col-span-4">
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
              Save Vendor
            </button>
          </div>
        </form>
      )}

      {editing && (
        <form
          onSubmit={(e) => void handleSaveEdit(e)}
          className="grid gap-3 rounded-xl border border-amber-200 bg-amber-50/40 p-4 sm:grid-cols-4"
        >
          <div className="sm:col-span-4">
            <h3 className="text-xs font-bold text-slate-900">Editing {editing.name}</h3>
          </div>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Tier</span>
            <select
              value={editTier}
              onChange={(e) => setEditTier(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
            >
              <option value="strategic">Strategic</option>
              <option value="preferred">Preferred</option>
              <option value="standard">Standard</option>
            </select>
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Status</span>
            <select
              value={editStatus}
              onChange={(e) => setEditStatus(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
            >
              <option value="active">Active</option>
              <option value="under_review">Under Review</option>
              <option value="offboarding">Offboarding</option>
            </select>
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Annual Spend ($)</span>
            <input
              type="number"
              value={editSpend}
              onChange={(e) => setEditSpend(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Notes</span>
            <input
              value={editNotes}
              onChange={(e) => setEditNotes(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
            />
          </label>
          <div className="flex justify-end gap-2 sm:col-span-4">
            <button
              type="button"
              onClick={() => setEditing(null)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white"
            >
              Save Changes
            </button>
          </div>
        </form>
      )}

      <div className="flex flex-wrap gap-1.5">
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setCategoryFilter(cat)}
            className={`rounded-full px-3 py-1 text-[11px] font-medium ${
              categoryFilter === cat
                ? 'bg-indigo-600 text-white'
                : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {visible.map((v) => (
          <div
            key={v.id}
            className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-indigo-600" />
                  <h3 className="text-sm font-bold text-slate-900">{v.name}</h3>
                </div>
                <button
                  type="button"
                  onClick={() => startEdit(v)}
                  className="inline-flex items-center gap-1 rounded border border-slate-200 px-2 py-0.5 text-[11px] text-slate-600 hover:bg-slate-50"
                >
                  <Edit3 className="h-3 w-3" />
                  Edit
                </button>
              </div>
              <p className="mt-1 text-[11px] text-slate-500">
                {v.category} &middot; Net {v.payment_terms_days}
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getBadgeTone(v.status)}`}
                >
                  {formatLabel(v.status)}
                </span>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                  {formatLabel(v.tier)} Tier
                </span>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                  Risk {v.risk_score}/100
                </span>
              </div>
              {v.notes && <p className="mt-2 text-xs text-slate-600">{v.notes}</p>}
            </div>

            <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-xs">
              <span className="text-slate-500">{v.primary_contact_name || 'No primary contact'}</span>
              <span className="font-bold text-slate-900">{formatCurrency(v.annual_spend)}/yr</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
