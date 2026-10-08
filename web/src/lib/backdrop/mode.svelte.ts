// Backdrop preference: 'signal' (animated ASCII) or 'still' (solid gradient only).
// Per-viewer convenience; storage may be unavailable, so every access is guarded.

export type BackdropMode = 'signal' | 'still';
const KEY = 'ghostjs8.backdrop';

function load(): BackdropMode {
  try {
    return localStorage.getItem(KEY) === 'still' ? 'still' : 'signal';
  } catch {
    return 'signal';
  }
}

class BackdropPref {
  mode = $state<BackdropMode>(typeof window === 'undefined' ? 'signal' : load());

  toggle(): void {
    this.mode = this.mode === 'signal' ? 'still' : 'signal';
    try {
      localStorage.setItem(KEY, this.mode);
    } catch {
      /* storage unavailable: preference lasts for this page only */
    }
  }
}

export const backdrop = new BackdropPref();
