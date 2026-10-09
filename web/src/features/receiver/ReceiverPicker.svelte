<script lang="ts">
  import Pill from '../../components/Pill.svelte';
  import { useApp } from '../../lib/state/context';
  import type { ReceiverDirectory } from '../../lib/protocol/generated';
  import { distanceKm, gridCenter, isProxied } from '../../lib/grid';

  let { onPicked }: { onPicked?: () => void } = $props();
  const app = useApp();
  let directory = $state<ReceiverDirectory | null>(null);
  let loadError = $state<string | null>(null);
  let query = $state('');
  let coversDial = $state<boolean>(true);
  let hideFull = $state<boolean>(true);
  let hideProxied = $state<boolean>(true);
  let manualHost = $state('');
  let manualPort = $state(8073);
  let manualPassword = $state('');
  let searchInput: HTMLInputElement | undefined = $state();

  export function focusSearch(): void {
    searchInput?.focus();
  }

  const dial = $derived(app.state.session?.tuning.dial_hz ?? 14_078_000);

  const home = $derived(gridCenter(app.state.ghostnet?.home_grid));

  const results = $derived.by(() => {
    const list = (directory?.receivers ?? []).map((r) => ({
      ...r,
      proxied: isProxied(r.host),
      km:
        home !== null && r.lat !== null && r.lon !== null ? distanceKm(home, [r.lon, r.lat]) : null,
    }));
    const q = query.trim().toLowerCase();
    return list
      .filter((r) => !coversDial || (r.min_hz <= dial && dial <= r.max_hz))
      .filter((r) => !hideFull || r.users < r.users_max)
      .filter((r) => !hideProxied || !r.proxied)
      .filter(
        (r) => !q || `${r.name} ${r.location} ${r.host} ${r.grid ?? ''}`.toLowerCase().includes(q),
      )
      .sort(
        (a, b) => (a.km ?? Infinity) - (b.km ?? Infinity) || (b.snr_db ?? -99) - (a.snr_db ?? -99),
      )
      .slice(0, 60);
  });

  async function load(): Promise<void> {
    loadError = null;
    try {
      const res = await fetch('/api/receivers');
      if (!res.ok) throw new Error(`HTTP ${String(res.status)}`);
      directory = (await res.json()) as ReceiverDirectory;
    } catch (err) {
      loadError = err instanceof Error ? err.message : String(err);
    }
  }

  function select(
    r: { host: string; port: number; name: string | null; tls?: boolean },
    password = '',
  ): void {
    app.send({
      v: 1,
      type: 'select_receiver',
      receiver: { host: r.host, port: r.port, name: r.name, tls: r.tls ?? false },
      password,
    });
    onPicked?.();
  }

  function connectManual(ev: SubmitEvent): void {
    ev.preventDefault();
    const host = manualHost.trim();
    if (!host) return;
    select({ host, port: manualPort, name: null }, manualPassword);
  }

  $effect(() => {
    void load();
  });
</script>

<div class="picker" data-testid="receiver-picker">
  <div class="toolbar">
    <label class="field grow">
      Public directory
      <input
        class="input"
        type="search"
        bind:this={searchInput}
        bind:value={query}
        placeholder="name, place, grid…"
      />
    </label>
    <div class="filters">
      <label><input type="checkbox" bind:checked={coversDial} /> covers dial</label>
      <label><input type="checkbox" bind:checked={hideFull} /> hide full</label>
      <label><input type="checkbox" bind:checked={hideProxied} /> hide proxied</label>
    </div>
  </div>
  {#if loadError}
    <p class="warn">Directory unavailable ({loadError}). Manual entry still works.</p>
  {:else if directory?.stale}
    <p class="warn">Directory refresh failed; showing the last good list.</p>
  {/if}

  <ul class="list" aria-label="Public receivers">
    {#each results as r (r.id)}
      {@const full = r.users >= r.users_max}
      <li>
        <button
          type="button"
          class="pick"
          onclick={() => {
            select(r);
          }}
          disabled={full}
          aria-describedby={`rx-${r.id}`}
        >
          <span class="name">{r.name}</span>
          <span class="meta mono" id={`rx-${r.id}`}>
            {r.location || r.host}{r.km !== null
              ? ` · ${Math.round(r.km).toLocaleString()} km`
              : ''} · {r.users}/{r.users_max} users{r.snr_db !== null
              ? ` · SNR ${String(r.snr_db)} dB`
              : ''}
          </span>
        </button>
        {#if full}<Pill tone="warn" label="full" />{/if}
        {#if r.proxied}<Pill
            tone="info"
            label="proxy"
            title="Behind proxy.kiwisdr.com: all proxied receivers share one host"
          />{/if}
      </li>
    {:else}
      <li class="muted">{directory ? 'No receivers match.' : 'Loading directory…'}</li>
    {/each}
  </ul>

  <details class="manual">
    <summary>Manual host:port</summary>
    <form onsubmit={connectManual}>
      <label class="field"
        >Host <input
          class="input"
          bind:value={manualHost}
          placeholder="kiwi.example.net"
          autocomplete="off"
        /></label
      >
      <label class="field"
        >Port <input
          class="input"
          type="number"
          min="1"
          max="65535"
          bind:value={manualPort}
        /></label
      >
      <label class="field"
        >Password (optional) <input
          class="input"
          type="password"
          bind:value={manualPassword}
          autocomplete="off"
        /></label
      >
      <button class="btn primary" type="submit">Listen</button>
    </form>
  </details>
</div>

<style>
  .picker {
    display: grid;
    gap: var(--g-space-3);
  }
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: var(--g-space-3) var(--g-space-5);
  }
  .grow {
    flex: 1 1 16rem;
    max-width: 28rem;
  }
  .muted {
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
  }
  .warn {
    color: var(--g-warn);
    font-size: var(--g-text-s);
    margin: 0;
  }
  .manual {
    font-size: var(--g-text-s);
  }
  summary {
    cursor: pointer;
    color: var(--g-chrome);
    font-size: var(--g-text-s);
    font-weight: 600;
  }
  form {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: var(--g-space-3);
    margin-top: var(--g-space-3);
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: var(--g-space-2) var(--g-space-4);
    min-height: 38px;
    align-items: center;
    font-size: var(--g-text-s);
    color: var(--g-text-muted);
  }
  .filters label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
    gap: 4px var(--g-space-3);
    max-height: clamp(240px, 46vh, 520px);
    overflow: auto;
  }
  .list li {
    display: flex;
    align-items: center;
    gap: var(--g-space-2);
    min-width: 0;
  }
  .list li.muted {
    grid-column: 1 / -1;
  }
  .pick {
    flex: 1;
    min-width: 0;
    display: grid;
    text-align: left;
    gap: 2px;
    padding: var(--g-space-2) var(--g-space-3);
    border: 1px solid transparent;
    border-radius: var(--g-radius-m);
    background: transparent;
    cursor: pointer;
    transition:
      background var(--g-dur-fast) var(--g-ease),
      border-color var(--g-dur-fast) var(--g-ease);
  }
  .pick:hover:not(:disabled) {
    border-color: var(--g-border);
    background: var(--g-glass-raised);
  }
  .pick:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
  .name {
    font-size: var(--g-text-s);
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meta {
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
