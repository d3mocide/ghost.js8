<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import Pill from '../../components/Pill.svelte';
  import { useApp } from '../../lib/state/context';
  import type { ReceiverDirectory } from '../../lib/protocol/generated';

  const app = useApp();
  let directory = $state<ReceiverDirectory | null>(null);
  let loadError = $state<string | null>(null);
  let query = $state('');
  let coversDial = $state<boolean>(true);
  let hideFull = $state<boolean>(true);
  let manualHost = $state('');
  let manualPort = $state(8073);
  let manualPassword = $state('');
  let searchInput: HTMLInputElement | undefined = $state();

  export function focusSearch(): void {
    searchInput?.focus();
  }

  const dial = $derived(app.state.session?.tuning.dial_hz ?? 14_078_000);
  const current = $derived(app.state.session?.receiver ?? null);

  const results = $derived.by(() => {
    const list = directory?.receivers ?? [];
    const q = query.trim().toLowerCase();
    return list
      .filter((r) => !coversDial || (r.min_hz <= dial && dial <= r.max_hz))
      .filter((r) => !hideFull || r.users < r.users_max)
      .filter(
        (r) => !q || `${r.name} ${r.location} ${r.host} ${r.grid ?? ''}`.toLowerCase().includes(q),
      )
      .sort((a, b) => (b.snr_db ?? -99) - (a.snr_db ?? -99))
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

  function select(r: { host: string; port: number; name: string | null }, password = ''): void {
    app.send({
      v: 1,
      type: 'select_receiver',
      receiver: { host: r.host, port: r.port, name: r.name },
      password,
    });
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

<Panel id="receiver" code="RX" title="Receiver">
  {#snippet actions()}
    {#if current}
      <button
        type="button"
        class="btn ghost"
        onclick={() => app.send({ v: 1, type: 'disconnect_receiver' })}
      >
        Release
      </button>
    {/if}
  {/snippet}

  <div class="current" data-testid="current-receiver">
    {#if current}
      <span class="mono host">{current.name ?? current.host}</span>
      <span class="mono muted">{current.host}:{current.port}</span>
    {:else}
      <span class="muted">No receiver selected.</span>
    {/if}
  </div>

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
      <button class="btn" type="submit">Listen</button>
    </form>
  </details>

  <div class="search">
    <label class="field">
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
    </div>
    {#if loadError}
      <p class="warn">Directory unavailable ({loadError}). Manual entry still works.</p>
    {:else if directory?.stale}
      <p class="warn">Directory refresh failed; showing the last good list.</p>
    {/if}
  </div>

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
            {r.location || r.host} · {r.users}/{r.users_max} users{r.snr_db !== null
              ? ` · SNR ${String(r.snr_db)} dB`
              : ''}
          </span>
        </button>
        {#if full}<Pill tone="warn" label="full" />{/if}
      </li>
    {:else}
      <li class="muted">{directory ? 'No receivers match.' : 'Loading directory…'}</li>
    {/each}
  </ul>
</Panel>

<style>
  .current {
    display: grid;
    gap: 2px;
    margin-bottom: var(--g-space-3);
  }
  .host {
    color: var(--g-signal);
  }
  .muted {
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
  }
  .warn {
    color: var(--g-warn);
    font-size: var(--g-text-s);
    margin: var(--g-space-2) 0 0;
  }
  .manual {
    margin-bottom: var(--g-space-3);
    font-size: var(--g-text-s);
  }
  summary {
    cursor: pointer;
    color: var(--g-chrome);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    letter-spacing: var(--g-tracking-caps);
    text-transform: uppercase;
  }
  form {
    display: grid;
    gap: var(--g-space-2);
    margin-top: var(--g-space-2);
  }
  .filters {
    display: flex;
    gap: var(--g-space-3);
    margin-top: var(--g-space-2);
    font-size: var(--g-text-s);
    color: var(--g-text-muted);
  }
  .list {
    list-style: none;
    margin: var(--g-space-3) 0 0;
    padding: 0;
    display: grid;
    gap: var(--g-space-1);
    max-height: 22rem;
    overflow: auto;
  }
  .list li {
    display: flex;
    align-items: center;
    gap: var(--g-space-2);
  }
  .pick {
    flex: 1;
    min-width: 0;
    display: grid;
    text-align: left;
    gap: 1px;
    padding: var(--g-space-2);
    border: 1px solid transparent;
    border-radius: var(--g-radius-s);
    background: rgb(255 255 255 / 0.02);
    cursor: pointer;
  }
  .pick:hover:not(:disabled) {
    border-color: var(--g-border-strong);
    background: var(--g-chrome-soft);
  }
  .pick:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
  .name {
    font-size: var(--g-text-s);
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
