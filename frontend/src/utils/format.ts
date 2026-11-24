export function formatCurrency(amount: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: amount % 1 === 0 ? 0 : 2,
  }).format(amount);
}

export function formatLabel(raw: string): string {
  return raw
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

export function getBadgeTone(value: string): string {
  const normalized = value.toLowerCase();
  if (
    normalized === 'critical' ||
    normalized === 'fail' ||
    normalized === 'blocked' ||
    normalized === 'rejected' ||
    normalized === 'overdue' ||
    normalized === 'outlier_high' ||
    normalized === 'deviation'
  ) {
    return 'bg-rose-50 text-rose-700 border-rose-200';
  }
  if (
    normalized === 'high' ||
    normalized === 'warning' ||
    normalized === 'redline_required' ||
    normalized === 'pending' ||
    normalized === 'pending_approval' ||
    normalized === 'notice_pending_approval' ||
    normalized === 'above_market' ||
    normalized === 'upcoming' ||
    normalized === 'missing'
  ) {
    return 'bg-amber-50 text-amber-800 border-amber-200';
  }
  if (
    normalized === 'low' ||
    normalized === 'pass' ||
    normalized === 'approved' ||
    normalized === 'favorable' ||
    normalized === 'compliant' ||
    normalized === 'below_market' ||
    normalized === 'competitive' ||
    normalized === 'healthy' ||
    normalized === 'notice_approved' ||
    normalized === 'renewed'
  ) {
    return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  }
  return 'bg-slate-100 text-slate-700 border-slate-200';
}
