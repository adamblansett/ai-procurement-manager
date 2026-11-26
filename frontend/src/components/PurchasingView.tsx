import { type ChangeEvent, type FormEvent, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, FileCheck2, PlusCircle, RefreshCw, Upload } from 'lucide-react';
import { procurementApi } from '../api/client';
import type {
  BudgetAccount,
  POLineItem,
  PurchaseOrder,
  Vendor,
  VendorQuote,
} from '../types/procurement';
import { formatCurrency, formatLabel, getBadgeTone } from '../utils/format';

interface PurchasingViewProps {
  vendors: Vendor[];
  onDataChange: () => Promise<void>;
}

export function PurchasingView({ vendors, onDataChange }: PurchasingViewProps) {
  const [budgets, setBudgets] = useState<BudgetAccount[]>([]);
  const [quotes, setQuotes] = useState<VendorQuote[]>([]);
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [selectedPo, setSelectedPo] = useState<PurchaseOrder | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showBudgetForm, setShowBudgetForm] = useState(false);
  const [showQuoteForm, setShowQuoteForm] = useState(false);

  const [newBudgetCode, setNewBudgetCode] = useState('CC-OPS-501');
  const [newBudgetDept, setNewBudgetDept] = useState('IT Operations');
  const [newBudgetAmt, setNewBudgetAmt] = useState('150000');
  const [newBudgetOwner, setNewBudgetOwner] = useState('Morgan Blake');

  const [newQuoteNum, setNewQuoteNum] = useState('QT-2026-901');
  const [newQuoteVendor, setNewQuoteVendor] = useState('');
  const [newQuoteValidUntil, setNewQuoteValidUntil] = useState('2027-01-31');
  const [newQuoteSku, setNewQuoteSku] = useState('CLD-K8S-NODE');
  const [newQuoteQty, setNewQuoteQty] = useState('5');
  const [newQuotePrice, setNewQuotePrice] = useState('3450');

  // Create PO form state
  const [poNumber, setPoNumber] = useState('PO-2026-1099');
  const [vendorId, setVendorId] = useState('');
  const [quoteId, setQuoteId] = useState('');
  const [costCenterCode, setCostCenterCode] = useState('');
  const [requesterName, setRequesterName] = useState('Jordan Ellis');
  const [skuCode, setSkuCode] = useState('CLD-K8S-NODE');
  const [description, setDescription] = useState('Compute Expansion');
  const [quantity, setQuantity] = useState('2');
  const [unitPrice, setUnitPrice] = useState('3500');

  const [justification, setJustification] = useState('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadPurchasing(selectId?: string) {
    try {
      const [budgetList, quoteList, poList] = await Promise.all([
        procurementApi.listBudgets(),
        procurementApi.listQuotes(),
        procurementApi.listPurchaseOrders(),
      ]);
      setBudgets(budgetList);
      setQuotes(quoteList);
      setOrders(poList);

      const targetId = selectId || selectedPo?.id || poList[0]?.id;
      const match = poList.find((p) => p.id === targetId) || poList[0] || null;
      setSelectedPo(match);
      if (!costCenterCode && budgetList.length > 0) {
        setCostCenterCode(budgetList[0].cost_center_code);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load purchasing records');
    }
  }

  useEffect(() => {
    void loadPurchasing();
  }, []);

  useEffect(() => {
    if (!vendorId && vendors.length > 0) {
      setVendorId(vendors[0].id);
      setNewQuoteVendor(vendors[0].id);
    }
  }, [vendors, vendorId]);

  async function handleCreateBudget(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await procurementApi.createBudget({
        cost_center_code: newBudgetCode,
        department: newBudgetDept,
        fiscal_year: 2026,
        annual_budget: Number(newBudgetAmt),
        committed_amount: 0,
        owner_name: newBudgetOwner,
      });
      setShowBudgetForm(false);
      setStatusMessage(`Created cost-center budget ${newBudgetCode}.`);
      await loadPurchasing();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Budget creation failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleBudgetsCsvUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await procurementApi.importBudgetsCsv(file);
      setStatusMessage(
        `Budgets CSV: ${res.imported_count} added, ${res.updated_count ?? 0} updated.`
      );
      await loadPurchasing();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Budgets CSV import failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateQuote(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const qtyNum = Number(newQuoteQty) || 1;
      const priceNum = Number(newQuotePrice) || 0;
      const created = await procurementApi.createQuote({
        vendor_id: newQuoteVendor || vendorId,
        quote_number: newQuoteNum,
        valid_until: newQuoteValidUntil,
        line_items: [
          {
            sku_code: newQuoteSku,
            description: `${newQuoteSku} Quoted Line`,
            quantity: qtyNum,
            unit_price: priceNum,
            line_total: Number((qtyNum * priceNum).toFixed(2)),
          },
        ],
      });
      setShowQuoteForm(false);
      setStatusMessage(`Registered quote ${created.quote_number}.`);
      await loadPurchasing();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Quote creation failed');
    } finally {
      setBusy(false);
    }
  }

  function handleSelectQuote(nextQuoteId: string) {
    setQuoteId(nextQuoteId);
    const quote = quotes.find((q) => q.id === nextQuoteId);
    if (quote) {
      setVendorId(quote.vendor_id);
      const firstLine = quote.line_items_json[0];
      if (firstLine) {
        setSkuCode(firstLine.sku_code);
        setDescription(firstLine.description);
        setQuantity(String(firstLine.quantity));
        setUnitPrice(String(firstLine.unit_price));
      }
    }
  }

  async function handleCreatePo(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setStatusMessage(null);
    try {
      const qtyNum = Number(quantity) || 1;
      const priceNum = Number(unitPrice) || 0;
      const line: POLineItem = {
        sku_code: skuCode,
        description,
        quantity: qtyNum,
        unit_price: priceNum,
        line_total: Number((qtyNum * priceNum).toFixed(2)),
      };
      const created = await procurementApi.createPurchaseOrder({
        po_number: poNumber,
        vendor_id: vendorId,
        quote_id: quoteId || null,
        cost_center_code: costCenterCode,
        requester_name: requesterName,
        line_items: [line],
      });
      setShowCreate(false);
      setPoNumber(`PO-2026-${Math.floor(1100 + Math.random() * 8000)}`);
      setSelectedPo(created);
      setStatusMessage(
        `Validated ${created.po_number}: ${created.validation_status.toUpperCase()}.`
      );
      await loadPurchasing(created.id);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PO creation failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleRevalidate() {
    if (!selectedPo) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await procurementApi.revalidatePurchaseOrder(selectedPo.id);
      setSelectedPo(updated);
      setStatusMessage(`Re-validated ${updated.po_number}.`);
      await loadPurchasing(updated.id);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Re-validation failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitApproval() {
    if (!selectedPo) return;
    setBusy(true);
    setError(null);
    try {
      const res = await procurementApi.submitPurchaseOrder(
        selectedPo.id,
        selectedPo.requester_name,
        justification || 'Submitted after validation checks.'
      );
      setStatusMessage(`Submitted for ${formatLabel(res.required_role)} approval.`);
      setJustification('');
      await loadPurchasing(selectedPo.id);
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission blocked');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            PO Validation &amp; Budget Controls
          </h2>
          <p className="text-xs text-slate-600">
            Verify line items against vendor quotes, cost-center headroom, benchmarks, and approval
            thresholds.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50">
            <Upload className="h-3.5 w-3.5" />
            <span>Import Budgets CSV</span>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => void handleBudgetsCsvUpload(e)}
              className="hidden"
            />
          </label>
          <button
            type="button"
            onClick={() => setShowBudgetForm((prev) => !prev)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            + Add Budget
          </button>
          <button
            type="button"
            onClick={() => setShowQuoteForm((prev) => !prev)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            + Add Quote
          </button>
          <button
            type="button"
            onClick={() => setShowCreate((prev) => !prev)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
          >
            <PlusCircle className="h-3.5 w-3.5" />
            Create &amp; Validate PO
          </button>
        </div>
      </div>

      {showBudgetForm && (
        <form
          onSubmit={(e) => void handleCreateBudget(e)}
          className="grid gap-3 rounded-xl border border-indigo-200 bg-white p-4 shadow-sm sm:grid-cols-5"
        >
          <input
            value={newBudgetCode}
            onChange={(e) => setNewBudgetCode(e.target.value)}
            placeholder="Cost Center Code"
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            required
          />
          <input
            value={newBudgetDept}
            onChange={(e) => setNewBudgetDept(e.target.value)}
            placeholder="Department"
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            required
          />
          <input
            type="number"
            value={newBudgetAmt}
            onChange={(e) => setNewBudgetAmt(e.target.value)}
            placeholder="Annual Budget ($)"
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            required
          />
          <input
            value={newBudgetOwner}
            onChange={(e) => setNewBudgetOwner(e.target.value)}
            placeholder="Owner"
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            required
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white"
          >
            Save Budget
          </button>
        </form>
      )}

      {showQuoteForm && (
        <form
          onSubmit={(e) => void handleCreateQuote(e)}
          className="grid gap-3 rounded-xl border border-indigo-200 bg-white p-4 shadow-sm sm:grid-cols-6"
        >
          <input
            value={newQuoteNum}
            onChange={(e) => setNewQuoteNum(e.target.value)}
            placeholder="Quote #"
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            required
          />
          <select
            value={newQuoteVendor || vendorId}
            onChange={(e) => setNewQuoteVendor(e.target.value)}
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
          >
            {vendors.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={newQuoteValidUntil}
            onChange={(e) => setNewQuoteValidUntil(e.target.value)}
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            required
          />
          <input
            value={newQuoteSku}
            onChange={(e) => setNewQuoteSku(e.target.value)}
            placeholder="SKU"
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            required
          />
          <div className="grid grid-cols-2 gap-1.5">
            <input
              type="number"
              value={newQuoteQty}
              onChange={(e) => setNewQuoteQty(e.target.value)}
              placeholder="Qty"
              className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
              required
            />
            <input
              type="number"
              value={newQuotePrice}
              onChange={(e) => setNewQuotePrice(e.target.value)}
              placeholder="Unit $"
              className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
              required
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white"
          >
            Save Quote
          </button>
        </form>
      )}

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

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {budgets.map((b) => {
          const usedPct = Math.min(
            100,
            Math.round((b.committed_amount / Math.max(1, b.annual_budget)) * 100)
          );
          return (
            <div key={b.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-indigo-700">
                  {b.cost_center_code}
                </span>
                <span className="text-[11px] font-semibold text-slate-500">{usedPct}% used</span>
              </div>
              <p className="mt-1 text-xs font-medium text-slate-900">{b.department}</p>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full ${usedPct >= 90 ? 'bg-rose-500' : 'bg-indigo-600'}`}
                  style={{ width: `${usedPct}%` }}
                />
              </div>
              <p className="mt-2 text-[11px] text-slate-500">
                Remaining: <strong className="text-slate-800">{formatCurrency(b.remaining_budget)}</strong>{' '}
                of {formatCurrency(b.annual_budget)}
              </p>
            </div>
          );
        })}
      </section>

      {showCreate && (
        <form
          onSubmit={(e) => void handleCreatePo(e)}
          className="space-y-3 rounded-xl border border-indigo-200 bg-white p-5 shadow-sm"
        >
          <h3 className="text-sm font-semibold text-slate-900">New Purchase Order Validation</h3>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-xs">
              <span className="font-medium text-slate-700">PO Number</span>
              <input
                value={poNumber}
                onChange={(e) => setPoNumber(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              />
            </label>
            <label className="text-xs">
              <span className="font-medium text-slate-700">Reference Quote (Optional)</span>
              <select
                value={quoteId}
                onChange={(e) => handleSelectQuote(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              >
                <option value="">No quote linked</option>
                {quotes.map((q) => (
                  <option key={q.id} value={q.id}>
                    {q.quote_number} — {q.vendor_name} ({formatCurrency(q.total_amount)})
                  </option>
                ))}
              </select>
            </label>
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
            <label className="text-xs">
              <span className="font-medium text-slate-700">Cost Center</span>
              <select
                value={costCenterCode}
                onChange={(e) => setCostCenterCode(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              >
                {budgets.map((b) => (
                  <option key={b.id} value={b.cost_center_code}>
                    {b.cost_center_code} — {b.department}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs">
              <span className="font-medium text-slate-700">Requester</span>
              <input
                value={requesterName}
                onChange={(e) => setRequesterName(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              />
            </label>
            <label className="text-xs">
              <span className="font-medium text-slate-700">SKU Code</span>
              <input
                value={skuCode}
                onChange={(e) => setSkuCode(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              />
            </label>
            <label className="text-xs">
              <span className="font-medium text-slate-700">Line Description</span>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              />
            </label>
            <label className="text-xs">
              <span className="font-medium text-slate-700">Quantity</span>
              <input
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              />
            </label>
            <label className="text-xs">
              <span className="font-medium text-slate-700">Unit Price ($)</span>
              <input
                type="number"
                step="0.01"
                value={unitPrice}
                onChange={(e) => setUnitPrice(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              />
            </label>
          </div>
          <div className="flex items-center justify-between border-t border-slate-100 pt-3 text-xs">
            <span className="font-semibold text-slate-700">
              Computed Total:{' '}
              {formatCurrency((Number(quantity) || 0) * (Number(unitPrice) || 0))}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-slate-600"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy}
                className="rounded-lg bg-indigo-600 px-4 py-1.5 font-semibold text-white hover:bg-indigo-700"
              >
                Create &amp; Run Rule Checks
              </button>
            </div>
          </div>
        </form>
      )}

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="space-y-2.5 lg:col-span-5">
          {orders.map((po) => {
            const active = selectedPo?.id === po.id;
            return (
              <button
                key={po.id}
                type="button"
                onClick={() => setSelectedPo(po)}
                className={`w-full rounded-xl border p-4 text-left transition ${
                  active
                    ? 'border-indigo-500 bg-indigo-50/40 ring-1 ring-indigo-500'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-bold text-slate-900">
                    {po.po_number}
                  </span>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getBadgeTone(po.validation_status)}`}
                  >
                    {formatLabel(po.validation_status)}
                  </span>
                </div>
                <p className="mt-1 text-xs font-medium text-slate-800">{po.vendor_name}</p>
                <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                  <span>
                    {po.cost_center_code} &middot; {formatCurrency(po.total_amount)}
                  </span>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${getBadgeTone(po.status)}`}
                  >
                    {formatLabel(po.status)}
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        <div className="lg:col-span-7">
          {selectedPo ? (
            <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-mono text-base font-bold text-slate-900">
                      {selectedPo.po_number}
                    </h3>
                    <span
                      className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${getBadgeTone(selectedPo.status)}`}
                    >
                      {formatLabel(selectedPo.status)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {selectedPo.vendor_name} &middot; Cost Center {selectedPo.cost_center_code} &middot;{' '}
                    Required Approver:{' '}
                    <strong className="text-slate-800">
                      {formatLabel(selectedPo.required_approver_role)}
                    </strong>
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-lg font-bold text-slate-900">
                    {formatCurrency(selectedPo.total_amount)}
                  </p>
                  <button
                    type="button"
                    onClick={() => void handleRevalidate()}
                    disabled={busy}
                    className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 hover:text-indigo-800"
                  >
                    <RefreshCw className="h-3 w-3" />
                    Re-validate
                  </button>
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                <span className="font-semibold text-indigo-700">Controller Risk Summary: </span>
                {selectedPo.ai_risk_summary}
              </div>

              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Validation Rule Checks
                </h4>
                {selectedPo.validation_issues_json.length === 0 ? (
                  <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                    <CheckCircle2 className="h-4 w-4" />
                    All line-item arithmetic, quote, budget, and benchmark checks passed.
                  </div>
                ) : (
                  selectedPo.validation_issues_json.map((issue, idx) => (
                    <div
                      key={`${issue.code}-${idx}`}
                      className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${getBadgeTone(issue.severity)}`}
                    >
                      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                      <div>
                        <span className="font-mono text-[11px] font-bold">{issue.code}: </span>
                        <span>{issue.message}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 text-[11px] uppercase text-slate-500">
                    <tr>
                      <th className="py-2">SKU</th>
                      <th className="py-2">Description</th>
                      <th className="py-2 text-right">Qty</th>
                      <th className="py-2 text-right">Unit Price</th>
                      <th className="py-2 text-right">Line Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {selectedPo.line_items_json.map((line, idx) => (
                      <tr key={`${line.sku_code}-${idx}`}>
                        <td className="py-2 font-mono font-semibold text-slate-800">
                          {line.sku_code}
                        </td>
                        <td className="py-2 text-slate-600">{line.description}</td>
                        <td className="py-2 text-right">{line.quantity}</td>
                        <td className="py-2 text-right">{formatCurrency(line.unit_price)}</td>
                        <td className="py-2 text-right font-semibold">
                          {formatCurrency(line.line_total)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {selectedPo.status === 'validated' && selectedPo.validation_status !== 'fail' && (
                <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                  <input
                    value={justification}
                    onChange={(e) => setJustification(e.target.value)}
                    placeholder="Optional finance approver justification..."
                    className="flex-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => void handleSubmitApproval()}
                    disabled={busy}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
                  >
                    <FileCheck2 className="h-3.5 w-3.5" />
                    Submit for Approval
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-xs text-slate-500">
              Select a purchase order to inspect rule checks.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
