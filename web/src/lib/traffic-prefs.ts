/** Per-viewer view of the decoded-traffic panel, remembered in this browser only. */
export interface TrafficPrefs {
  readonly directedOnly: boolean;
  readonly threaded: boolean;
}

export const TRAFFIC_PREFS_KEY = 'ghostjs8.traffic.v1';
/** Directed messages are the signal; raw activity frames are the noise around them. */
export const DEFAULT_TRAFFIC_PREFS: TrafficPrefs = { directedOnly: true, threaded: false };

export function parseTrafficPrefs(raw: string | null): TrafficPrefs {
  if (raw === null) return DEFAULT_TRAFFIC_PREFS;
  try {
    const v: unknown = JSON.parse(raw);
    if (typeof v !== 'object' || v === null) return DEFAULT_TRAFFIC_PREFS;
    const o = v as Record<string, unknown>;
    return {
      directedOnly:
        typeof o['directedOnly'] === 'boolean'
          ? o['directedOnly']
          : DEFAULT_TRAFFIC_PREFS.directedOnly,
      threaded: typeof o['threaded'] === 'boolean' ? o['threaded'] : DEFAULT_TRAFFIC_PREFS.threaded,
    };
  } catch {
    return DEFAULT_TRAFFIC_PREFS;
  }
}

export function loadTrafficPrefs(): TrafficPrefs {
  try {
    return parseTrafficPrefs(localStorage.getItem(TRAFFIC_PREFS_KEY));
  } catch {
    return DEFAULT_TRAFFIC_PREFS; // storage blocked: private window, site data off
  }
}

export function saveTrafficPrefs(p: TrafficPrefs): void {
  try {
    localStorage.setItem(TRAFFIC_PREFS_KEY, JSON.stringify(p));
  } catch {
    /* a preference is not worth an error */
  }
}
