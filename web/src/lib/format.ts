/** Display formatting. All UI times are UTC. */

/** 14078000 -> "14.078 000" (MHz with a thin grouping, like JS8Call). */
export function formatMHz(hz: number): string {
  const khz = Math.floor(hz / 1000);
  const mhz = Math.floor(khz / 1000);
  const rest = String(khz % 1000).padStart(3, '0');
  const sub = String(Math.round(hz % 1000)).padStart(3, '0');
  return `${String(mhz)}.${rest} ${sub}`;
}

export function formatKHz(hz: number): string {
  return (hz / 1000).toFixed(3);
}

export function formatSnr(db: number | null | undefined): string {
  if (db === null || db === undefined) return '—';
  return `${db >= 0 ? '+' : '−'}${String(Math.abs(db)).padStart(2, '0')}`;
}

export function utcTime(iso: string | Date, seconds = true): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  const s = d.toISOString();
  return seconds ? s.slice(11, 19) : s.slice(11, 16);
}

export function utcDateTime(iso: string): string {
  const s = new Date(iso).toISOString();
  return `${s.slice(0, 10)} ${s.slice(11, 19)}Z`;
}

/** "12s", "4m", "3h", "2d" ago. */
export function ago(iso: string | null | undefined, now: number): string {
  if (!iso) return 'never';
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 60) return `${String(s)}s`;
  if (s < 3600) return `${String(Math.floor(s / 60))}m`;
  if (s < 86400) return `${String(Math.floor(s / 3600))}h`;
  return `${String(Math.floor(s / 86400))}d`;
}
