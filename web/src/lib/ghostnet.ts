/** GhostNet helpers: traffic classification and countdowns. Pure, unit-tested. */

export interface TrafficTags {
  /** @GSTFLASH: emergency flash traffic, relay to highest level HQ within range. */
  readonly flash: boolean;
  /** @GHOSTNET or a regional @GN<country><state> group. */
  readonly ghostnet: boolean;
  /** The regional group, e.g. "@GNUSASC", if present. */
  readonly regional: string | null;
}

const FLASH = /(^|[\s:])@GSTFLASH\b/i;
const GHOSTNET = /(^|[\s:])@GHOSTNET\b/i;
const REGIONAL = /(^|[\s:])(@GN[A-Z]{3}[A-Z]{0,2})\b/i;

export function classify(text: string): TrafficTags {
  const regional = REGIONAL.exec(text)?.[2]?.toUpperCase() ?? null;
  return { flash: FLASH.test(text), ghostnet: GHOSTNET.test(text) || regional !== null, regional };
}

/** "3d 04h", "2h 05m", "12m 05s", "45s". */
export function countdown(fromMs: number, toMs: number): string {
  let s = Math.max(0, Math.round((toMs - fromMs) / 1000));
  const d = Math.floor(s / 86400);
  s -= d * 86400;
  const h = Math.floor(s / 3600);
  s -= h * 3600;
  const m = Math.floor(s / 60);
  s -= m * 60;
  const p = (n: number): string => String(n).padStart(2, '0');
  if (d > 0) return `${String(d)}d ${p(h)}h`;
  if (h > 0) return `${String(h)}h ${p(m)}m`;
  if (m > 0) return `${String(m)}m ${p(s)}s`;
  return `${String(s)}s`;
}

/** Local wall-clock rendering of a UTC instant, for "Thursday night" sanity. */
export function localWhen(iso: string, locale?: string): string {
  return new Date(iso).toLocaleString(locale, {
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const REGION_LABEL: Record<'na' | 'eu' | 'aus', string> = {
  na: 'North America',
  eu: 'Europe',
  aus: 'Australia',
};

/** Parse "#/nets/<id>" routes. Only ids the bridge generates are accepted. */
export function netIdFromHash(hash: string): string | null {
  const m = /^#\/nets\/([a-z0-9-]{1,40}-\d{8}T\d{4}Z)$/.exec(hash);
  return m?.[1] ?? null;
}
