import { getContext, setContext } from 'svelte';
import type { GhostApp } from './app.svelte';

const KEY = Symbol('ghost.js8 app');

export function provideApp(app: GhostApp): void {
  setContext(KEY, app);
}

export function useApp(): GhostApp {
  const app = getContext<GhostApp | undefined>(KEY);
  if (!app) throw new Error('GhostApp context missing');
  return app;
}
