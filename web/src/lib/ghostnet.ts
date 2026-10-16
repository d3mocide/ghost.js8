/** GhostNet helpers: traffic classification, countdowns, autopilot settings. Pure, unit-tested. */

import type {
  GhostNetWindowSetting,
  GhostNetWindowUpdate,
  ReceiverRef,
  SetGhostNetSettings,
} from './protocol/generated';

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

const WEEKDAY = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;

/** "Fri 01:00–01:30Z": a plan window's weekly slot in UTC (the end may fall on the next day). */
export function windowWhen(
  w: Pick<GhostNetWindowSetting, 'weekday' | 'start' | 'minutes'>,
): string {
  const [hh = '0', mm = '0'] = w.start.split(':');
  const end = (Number(hh) * 60 + Number(mm) + w.minutes) % 1440;
  const p = (n: number): string => String(n).padStart(2, '0');
  const day = WEEKDAY[((w.weekday % 7) + 7) % 7] ?? '';
  return `${day} ${w.start}–${p(Math.floor(end / 60))}:${p(end % 60)}Z`;
}

/** A receiver for display: its name when it has one, else host:port. */
export function receiverLabel(r: Pick<ReceiverRef, 'host' | 'port' | 'name'>): string {
  return r.name?.trim() || `${r.host}:${String(r.port)}`;
}

export function sameReceiver(
  a: Pick<ReceiverRef, 'host' | 'port'> | null | undefined,
  b: Pick<ReceiverRef, 'host' | 'port'> | null | undefined,
): boolean {
  return a != null && b != null && a.host === b.host && a.port === b.port;
}

export interface WindowChange {
  enabled?: boolean;
  /** Prefer this receiver for the window. */
  receiver?: ReceiverRef;
  /** Back to the picker's automatic choice. */
  clearReceiver?: boolean;
}

export interface SettingsChange {
  autopilotEnabled?: boolean;
  park?: boolean;
  recordAudio?: boolean;
  windows?: Readonly<Record<string, WindowChange>>;
}

/**
 * A complete `ghostnet_settings` message. The contract requires every field, so anything the
 * change does not mention is sent as `null`, which the bridge reads as "leave it alone".
 */
export function settingsMessage(change: SettingsChange): SetGhostNetSettings {
  const windows: Record<string, GhostNetWindowUpdate> = {};
  for (const [id, w] of Object.entries(change.windows ?? {})) {
    windows[id] = {
      enabled: w.enabled ?? null,
      receiver: w.receiver ?? null,
      clear_receiver: w.clearReceiver ?? false,
    };
  }
  return {
    v: 1,
    type: 'ghostnet_settings',
    autopilot_enabled: change.autopilotEnabled ?? null,
    park: change.park ?? null,
    record_audio: change.recordAudio ?? null,
    windows,
  };
}
