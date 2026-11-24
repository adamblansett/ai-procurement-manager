import { type FormEvent, useEffect, useState } from 'react';
import { BarChart3, PlusCircle, Sparkles } from 'lucide-react';
import { procurementApi } from '../api/client';
import type {
  BenchmarkSummary,
  PricingBenchmark,
  QuoteAnalysisResult,
  Vendor,
} from '../types/procurement';
import { formatCurrency, formatLabel, getBadgeTone } from '../utils/format';

interface BenchmarksViewProps {
  vendors: Vendor[];
  onDataChange: () => Promise<void>;
}

export function BenchmarksView({ vendors, onDataChange }: BenchmarksViewProps) {
  const [benchmarks, setBenchmarks] = useState<PricingBenchmark[]>([]);
  const [summaries, setSummaries] = useState<BenchmarkSummary[]>([]);
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [showAdd, setShowAdd] = useState(false);

  // Quote analyzer state
  const [skuCode, setSkuCode] = useState('CRM-ENT-SEAT');
  const [category, setCategory] = useState('SaaS Applications');
  const [unitType, setUnitType] = useState('seat/month');
  const [volumeTier, setVolumeTier] = useState('51-250');
  const [quantity, setQuantity] = useState('150');
  const [proposedPrice, setProposedPrice] = useState('165');
  const [proposedUplift, setProposedUplift] = useState('8.5');
  const [analysis, setAnalysis] = useState<QuoteAnalysisResult | null>(null);

  // Add benchmark state
  const [newSku, setNewSku] = useState('');
  const [newSkuName, setNewSkuName] = useState('');
  const [newCategory, setNewCategory] = useState('SaaS Applications');
  const [newUnitType, setNewUnitType] = useState('seat/month');
  const [newTier, setNewTier] = useState('51-250');
  const [newPrice, setNewPrice] = useState('');
  const [newUplift, setNewUplift] = useState('3.0');
  const [newDiscount, setNewDiscount] = useState('15.0');
  const [newVendorId, setNewVendorId] = useState('');

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadBenchmarks() {
    try {
      const [rows, summaryRows] = await Promise.all([
        procurementApi.listBenchmarks(),
        procurementApi.getBenchmarkSummary(),
      ]);
      setBenchmarks(rows);
      setSummaries(summaryRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load benchmarks');
    }
  }

  useEffect(() => {
    void loadBenchmarks();
  }, []);

  async function handleAnalyze(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await procurementApi.analyzeQuote({
        sku_code: skuCode.trim() || undefined,
        category,
        unit_type: unitType,
        volume_tier: volumeTier,
        quantity: Number(quantity) || 1,
        proposed_unit_price: Number(proposedPrice),
        proposed_uplift_pct: Number(proposedUplift) || 0,
      });
      setAnalysis(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Quote analysis failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleAddBenchmark(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await procurementApi.createBenchmark({
        vendor_id: newVendorId || null,
        sku_code: newSku,
        sku_name: newSkuName,
        category: newCategory,
        unit_type: newUnitType,
        volume_tier: newTier,
        quoted_unit_price: Number(newPrice),
        annual_uplift_pct: Number(newUplift) || 0,
        discount_pct: Number(newDiscount) || 0,
        source: 'historical_quote',
        effective_year: 2026,
      });
      setShowAdd(false);
      setNewSku('');
      setNewSkuName('');
      setNewPrice('');
      await loadBenchmarks();
      await onDataChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to record benchmark');
    } finally {
      setBusy(false);
    }
  }

  const categories = ['ALL', ...Array.from(new Set(benchmarks.map((b) => b.category)))];
  const visibleBenchmarks =
    categoryFilter === 'ALL'
      ? benchmarks
      : benchmarks.filter((b) => b.category === categoryFilter);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Pricing Benchmarks &amp; Quote Analysis
          </h2>
          <p className="text-xs text-slate-600">
            Compare proposed unit rates and annual escalators against historical executed contracts.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAdd((prev) => !prev)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
        >
          <PlusCircle className="h-3.5 w-3.5" />
          Add Benchmark Quote
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-xs text-rose-800">
          {error}
        </div>
      )}

      {showAdd && (
        <form
          onSubmit={(e) => void handleAddBenchmark(e)}
          className="grid gap-3 rounded-xl border border-indigo-200 bg-white p-5 shadow-sm sm:grid-cols-4"
        >
          <label className="text-xs">
            <span className="font-medium text-slate-700">SKU Code</span>
            <input
              value={newSku}
              onChange={(e) => setNewSku(e.target.value)}
              placeholder="CRM-ENT-SEAT"
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">SKU Name</span>
            <input
              value={newSkuName}
              onChange={(e) => setNewSkuName(e.target.value)}
              placeholder="Enterprise CRM Seat"
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Category</span>
            <input
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Vendor (Optional)</span>
            <select
              value={newVendorId}
              onChange={(e) => setNewVendorId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            >
              <option value="">Market / Peer Cohort</option>
              {vendors.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Unit Type</span>
            <input
              value={newUnitType}
              onChange={(e) => setNewUnitType(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Volume Tier</span>
            <select
              value={newTier}
              onChange={(e) => setNewTier(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            >
              <option value="1-50">1-50</option>
              <option value="51-250">51-250</option>
              <option value="251-1000">251-1000</option>
              <option value="1000+">1000+</option>
            </select>
          </label>
          <label className="text-xs">
            <span className="font-medium text-slate-700">Unit Price ($)</span>
            <input
              type="number"
              step="0.01"
              value={newPrice}
              onChange={(e) => setNewPrice(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              required
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs">
              <span className="font-medium text-slate-700">Uplift %</span>
              <input
                type="number"
                step="0.1"
                value={newUplift}
                onChange={(e) => setNewUplift(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
              />
            </label>
            <label className="text-xs">
              <span className="font-medium text-slate-700">Discount %</span>
              <input
                type="number"
                step="0.1"
                value={newDiscount}
                onChange={(e) => setNewDiscount(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
              />
            </label>
          </div>
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
              Save Benchmark
            </button>
          </div>
        </form>
      )}

      <section className="grid gap-6 lg:grid-cols-12">
        <form
          onSubmit={(e) => void handleAnalyze(e)}
          className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-5"
        >
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-600" />
            <h3 className="text-sm font-semibold text-slate-900">Quote Benchmark Analyzer</h3>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs">
              <span className="font-medium text-slate-700">SKU Code</span>
              <input
                value={skuCode}
                onChange={(e) => setSkuCode(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
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
              <span className="font-medium text-slate-700">Unit Type</span>
              <input
                value={unitType}
                onChange={(e) => setUnitType(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              />
            </label>
            <label className="text-xs">
              <span className="font-medium text-slate-700">Volume Tier</span>
              <select
                value={volumeTier}
                onChange={(e) => setVolumeTier(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
              >
                <option value="1-50">1-50</option>
                <option value="51-250">51-250</option>
                <option value="251-1000">251-1000</option>
                <option value="1000+">1000+</option>
              </select>
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
              <span className="font-medium text-slate-700">Proposed Unit Price ($)</span>
              <input
                type="number"
                step="0.01"
                value={proposedPrice}
                onChange={(e) => setProposedPrice(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                required
              />
            </label>
          </div>
          <label className="block text-xs">
            <span className="font-medium text-slate-700">Proposed Annual Uplift (%)</span>
            <input
              type="number"
              step="0.1"
              value={proposedUplift}
              onChange={(e) => setProposedUplift(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? 'Analyzing Quote...' : 'Analyze Quote vs Market'}
          </button>
        </form>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-7">
          {analysis ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">Benchmark Verdict</h3>
                  <p className="text-[11px] text-slate-500">
                    Matched by {formatLabel(analysis.matched_by)} ({analysis.sample_size} peer quotes)
                  </p>
                </div>
                <span
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${getBadgeTone(analysis.rating)}`}
                >
                  {formatLabel(analysis.rating)} ({analysis.variance_vs_median_pct > 0 ? '+' : ''}
                  {analysis.variance_vs_median_pct}% vs median)
                </span>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg bg-slate-50 p-3">
                  <p className="text-[11px] text-slate-500">Market Median / P25</p>
                  <p className="mt-1 text-sm font-bold text-slate-900">
                    {formatCurrency(analysis.median_price)} / {formatCurrency(analysis.p25_price)}
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 p-3">
                  <p className="text-[11px] text-slate-500">Estimated Annual Spend</p>
                  <p className="mt-1 text-sm font-bold text-slate-900">
                    {formatCurrency(analysis.estimated_annual_spend)}
                  </p>
                </div>
                <div className="rounded-lg bg-emerald-50 p-3">
                  <p className="text-[11px] text-emerald-700">Potential Annual Savings</p>
                  <p className="mt-1 text-sm font-bold text-emerald-800">
                    {formatCurrency(analysis.potential_annual_savings)}
                  </p>
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between text-[11px] text-slate-500">
                  <span>Min {formatCurrency(analysis.min_price)}</span>
                  <span>P25 {formatCurrency(analysis.p25_price)}</span>
                  <span>Median {formatCurrency(analysis.median_price)}</span>
                  <span>P75 {formatCurrency(analysis.p75_price)}</span>
                  <span>Max {formatCurrency(analysis.max_price)}</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-indigo-600"
                    style={{ width: `${Math.min(100, Math.max(8, analysis.percentile_rank))}%` }}
                  />
                </div>
              </div>

              <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3.5 text-xs">
                <p className="font-medium text-slate-800">{analysis.negotiation_recommendation}</p>
                <p className="text-slate-600">{analysis.uplift_assessment}</p>
              </div>
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center py-10 text-center">
              <BarChart3 className="h-8 w-8 text-slate-300" />
              <p className="mt-2 text-xs font-medium text-slate-600">
                Run Quote Benchmark Analyzer to inspect P25/median variance and annual savings.
              </p>
            </div>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
          <h3 className="text-sm font-semibold text-slate-900">
            SKU Percentile Summary ({summaries.length} SKUs)
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {categories.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setCategoryFilter(cat)}
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                  categoryFilter === cat
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-100 bg-slate-50 text-[11px] uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2.5">SKU</th>
                <th className="px-4 py-2.5">Category</th>
                <th className="px-4 py-2.5">Samples</th>
                <th className="px-4 py-2.5">P25</th>
                <th className="px-4 py-2.5">Median</th>
                <th className="px-4 py-2.5">P75</th>
                <th className="px-4 py-2.5">Avg Uplift</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {summaries.map((item) => (
                <tr key={`${item.sku_code}-${item.unit_type}`}>
                  <td className="px-4 py-2.5 font-semibold text-slate-900">
                    {item.sku_code}
                    <div className="text-[11px] font-normal text-slate-500">
                      {item.sku_name} ({item.unit_type})
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">{item.category}</td>
                  <td className="px-4 py-2.5">{item.sample_size}</td>
                  <td className="px-4 py-2.5 font-medium text-emerald-700">
                    {formatCurrency(item.p25_price)}
                  </td>
                  <td className="px-4 py-2.5 font-semibold text-slate-900">
                    {formatCurrency(item.median_price)}
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">{formatCurrency(item.p75_price)}</td>
                  <td className="px-4 py-2.5 text-slate-600">{item.avg_uplift_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-400">
          Showing {visibleBenchmarks.length} underlying historical benchmark records.
        </div>
      </section>
    </div>
  );
}
