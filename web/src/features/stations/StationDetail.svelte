<script lang="ts">
  // Everything the store knows about one callsign: who it talked to, what it sent, and
  // how it has been heard. Shown inside the Heard stations card in place of its table.
  import { useApp } from '../../lib/state/context';
  import { selection } from '../../lib/state/selection.svelte';
  import { ago, formatSnr, utcDateTime } from '../../lib/format';
  import { distanceKm, gridCenter, normalizeGrid } from '../../lib/grid';
  import { bearingDeg, compass } from '../../lib/geo';
  import { speedChip } from '../../lib/traffic';
  import type { StationHistory } from '../../lib/protocol/generated';

  const app = useApp();
  const call = $derived(selection.call);
  let history = $state<StationHistory | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);

  $effect(() => {
    const c = call;
    history = null;
    error = null;
    if (!c) return;
    const ctl = new AbortController();
    loading = true;
    void (async () => {
      try {
        const res = await fetch(`/api/stations/${encodeURIComponent(c)}`, { signal: ctl.signal });
        if (!res.ok)
          throw new Error(res.status === 404 ? 'not a callsign' : `HTTP ${String(res.status)}`);
        history = (await res.json()) as StationHistory;
      } catch (err) {
        if (!ctl.signal.aborted) error = err instanceof Error ? err.message : String(err);
      } finally {
        if (!ctl.signal.aborted) loading = false;
      }
    })();
    return () => {
      ctl.abort();
    };
  });

  // Prefer the live record: it updates as the station is heard again.
  const live = $derived(call ? (app.state.stations[call] ?? null) : null);
  const info = $derived(live ?? history?.station ?? null);
  const grid = $derived(normalizeGrid(info?.grid));
  const home = $derived(gridCenter(app.state.ghostnet?.home_grid));
  const where = $derived.by(() => {
    const c = gridCenter(grid);
    if (!home || !c) return null;
    const bearing = Math.round(bearingDeg(home, c));
    return `${Math.round(distanceKm(home, c)).toLocaleString()} km ${compass(bearing)} (${String(bearing)}°)`;
  });

  function onKey(e: KeyboardEvent): void {
    if (call && e.key === 'Escape') selection.close();
  }
</script>

<svelte:window onkeydown={onKey} />

{#if call}
  <div class="detail" data-testid="station-detail" aria-label={`History for ${call}`}>
    <h3 class="mono">{call}</h3>

    <dl class="facts mono">
      {#if grid}<div>
          <dt>Grid</dt>
          <dd>{grid}</dd>
        </div>{/if}
      {#if where}<div>
          <dt>From home</dt>
          <dd>{where}</dd>
        </div>{/if}
      {#if info}
        <div>
          <dt>Last heard</dt>
          <dd>{ago(info.last_heard_utc, app.now)} ago</dd>
        </div>
        <div>
          <dt>Last SNR</dt>
          <dd>{formatSnr(info.snr_db)} dB</dd>
        </div>
        <div>
          <dt>Heard</dt>
          <dd>{info.heard_count}×</dd>
        </div>
      {/if}
      {#if history}
        <div>
          <dt>Sent</dt>
          <dd>{history.sent}</dd>
        </div>
        <div>
          <dt>Addressed</dt>
          <dd>{history.received}</dd>
        </div>
      {/if}
    </dl>

    {#if loading}
      <p class="muted">Loading…</p>
    {:else if error}
      <p class="warn">Could not load history ({error}).</p>
    {:else if history}
      {#if history.decodes.length === 0}
        <p class="muted">No messages from or to {call} in the store.</p>
      {:else}
        <ol class="log" aria-label={`Messages sent by or to ${call}`}>
          {#each history.decodes as d, i (`${d.utc}-${String(i)}`)}
            {@const sent = d.from_call === history.callsign}
            <li>
              <div class="meta mono">
                <time datetime={d.utc}>{utcDateTime(d.utc).slice(5, 19)}Z</time>
                <span>{formatSnr(d.snr_db)} dB</span>
                <span>{d.offset_hz} Hz</span>
                {#if speedChip(d.speed)}<span class="chip spd">{speedChip(d.speed)}</span>{/if}
              </div>
              <div class="msg mono">
                <span
                  class="dirn"
                  title={sent ? 'Sent by this station' : 'Addressed to this station'}
                  >{sent ? '→' : '←'}</span
                >
                {#if sent && d.to_call}<button
                    type="button"
                    class="who"
                    onclick={() => {
                      if (d.to_call && !d.to_call.startsWith('@')) selection.open(d.to_call);
                    }}>{d.to_call}</button
                  >{:else if !sent && d.from_call}<button
                    type="button"
                    class="who"
                    onclick={() => {
                      if (d.from_call) selection.open(d.from_call);
                    }}>{d.from_call}</button
                  >{/if}
                {d.text}
              </div>
            </li>
          {/each}
        </ol>
      {/if}
    {/if}
  </div>
{/if}

<style>
  .detail {
    display: flex;
    flex-direction: column;
    gap: var(--g-space-3);
    padding: 0 var(--g-space-4) var(--g-space-4);
  }
  h3 {
    margin: 0;
    font-size: 1.3rem;
    font-weight: 600;
    color: var(--g-accent-a);
  }
  .facts {
    display: flex;
    flex-wrap: wrap;
    gap: var(--g-space-2) var(--g-space-5);
    margin: 0;
    font-size: var(--g-text-xs);
  }
  .facts dt {
    color: var(--g-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 10px;
  }
  .facts dd {
    margin: 0;
    color: var(--g-text);
  }
  .log {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow: auto;
    max-height: clamp(280px, 60vh, 640px);
  }
  .log li {
    padding: var(--g-space-2) 0;
    border-top: 1px solid var(--g-hairline);
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--g-space-3);
    align-items: center;
    color: var(--g-text-muted);
    font-size: 10.5px;
  }
  .msg {
    margin-top: 2px;
    font-size: var(--g-text-s);
    overflow-wrap: anywhere;
  }
  .dirn {
    color: var(--g-signal);
    margin-right: 4px;
  }
  .who {
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    font-weight: 600;
    color: var(--g-accent-a);
    cursor: pointer;
  }
  .who:hover {
    text-decoration: underline;
  }
  .muted,
  .warn {
    margin: 0;
    font-size: var(--g-text-s);
    color: var(--g-text-muted);
  }
  .warn {
    color: var(--g-warn);
  }
</style>
