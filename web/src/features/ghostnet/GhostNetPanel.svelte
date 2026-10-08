<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import Pill from '../../components/Pill.svelte';
  import type { PillTone } from '../../components/pill';
  import { useApp } from '../../lib/state/context';
  import { countdown, localWhen, REGION_LABEL } from '../../lib/ghostnet';
  import { formatMHz, utcDateTime } from '../../lib/format';
  import type { GhostNet, NetSummary } from '../../lib/protocol/generated';

  const app = useApp();
  const g = $derived(app.state.ghostnet);
  let nets = $state<NetSummary[]>([]);
  let loadError = $state<string | null>(null);

  const MODE: Record<GhostNet['mode'], readonly [PillTone, string]> = {
    window: ['ok', 'ON NET'],
    parked: ['info', 'WATCHING 7.107'],
    paused: ['warn', 'PAUSED — MANUAL'],
    off: ['unknown', 'AUTOPILOT OFF'],
  };
  const mode = $derived(MODE[g?.mode ?? 'off']);
  const target = $derived(g?.window ?? g?.next_window ?? null);
  const inWindow = $derived(target !== null && g?.window !== null && g?.window !== undefined);
  const started = $derived(target ? Date.parse(target.start) <= app.now : false);

  async function load(): Promise<void> {
    try {
      const res = await fetch('/api/nets');
      if (!res.ok) throw new Error(`HTTP ${String(res.status)}`);
      nets = (await res.json()) as NetSummary[];
      loadError = null;
    } catch (err) {
      loadError = err instanceof Error ? err.message : String(err);
    }
  }

  // Reload the log list on mount and whenever a recording starts or ends.
  let lastRecording: string | null | undefined;
  $effect(() => {
    const rec = g?.recording_net_id ?? null;
    if (rec !== lastRecording) {
      lastRecording = rec;
      void load();
    }
  });
</script>

<Panel id="ghostnet" code="GN" title="GhostNet">
  {#snippet actions()}
    <Pill tone={mode[0]} label={mode[1]} />
  {/snippet}

  {#if !g || !g.enabled}
    <p class="muted">{g?.detail ?? 'Waiting for the bridge…'}</p>
    <p class="help">
      Set <code>GHOSTJS8_GHOSTNET=on</code>, <code>GHOSTJS8_GHOSTNET_REGION</code> and
      <code>GHOSTJS8_HOME_GRID</code> to monitor and record the nets automatically.
    </p>
  {:else}
    <div class="region mono">
      {REGION_LABEL[g.region ?? 'na']} · home {g.home_grid}
    </div>

    {#if target}
      <div class="window" class:live={inWindow}>
        <div class="label">
          {#if g.recording_net_id}<span class="rec" aria-label="recording"
              ><span aria-hidden="true">●</span> REC</span
            >{/if}
          {target.label}
        </div>
        <div class="mono freq">{target.band} · {formatMHz(target.dial_hz)} MHz USB</div>
        <div class="when mono">
          {#if inWindow && started}
            ends in <strong>{countdown(app.now, Date.parse(target.end))}</strong>
          {:else}
            {inWindow ? 'pre-roll · starts in' : 'next in'}
            <strong>{countdown(app.now, Date.parse(target.start))}</strong>
          {/if}
        </div>
        <div class="times">
          {utcDateTime(target.start)} · local {localWhen(target.start)}
        </div>
      </div>
    {/if}

    {#if g.receiver_reason}<p class="muted small">Receiver: {g.receiver_reason}</p>{/if}
    {#if g.mode === 'paused' && g.paused_until}
      <p class="warn small">
        A viewer took manual control; autopilot resumes {utcDateTime(g.paused_until)}.
      </p>
    {/if}
    {#if g.detail}<p class="warn small">{g.detail}</p>{/if}
  {/if}

  <h3 class="caps">Recorded nets</h3>
  {#if loadError}
    <p class="warn small">Could not load recordings ({loadError}).</p>
  {:else if nets.length === 0}
    <p class="muted small">No nets recorded yet.</p>
  {:else}
    <ul class="nets" data-testid="net-list">
      {#each nets as n (n.id)}
        <li>
          <a href={`#/nets/${n.id}`} data-testid="net-link">
            <span class="name">{n.label}</span>
            <span class="meta mono">
              {utcDateTime(n.scheduled_start)} · {n.decode_count} decodes · {n.station_count} stations
              {#if n.ended === null}· <span class="live">recording</span>{/if}
            </span>
          </a>
          {#if n.flash_count > 0}<Pill tone="alert" label={`${String(n.flash_count)} flash`} />{/if}
        </li>
      {/each}
    </ul>
  {/if}
</Panel>

<style>
  .region {
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
    margin-bottom: var(--g-space-2);
  }
  .window {
    display: grid;
    gap: 2px;
    padding: var(--g-space-2) var(--g-space-3);
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-s);
    background: rgb(5 6 10 / 0.45);
  }
  .window.live {
    border-color: rgb(61 255 154 / 0.5);
    box-shadow: inset 0 0 18px rgb(61 255 154 / 0.08);
  }
  .label {
    font-size: var(--g-text-s);
    display: flex;
    gap: var(--g-space-2);
    align-items: center;
  }
  .rec {
    color: var(--g-alert);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    letter-spacing: 0.1em;
    animation: blink 1.6s steps(2, start) infinite;
  }
  .freq {
    color: var(--g-signal);
    font-size: var(--g-text-s);
  }
  .when {
    font-size: var(--g-text-s);
    color: var(--g-text);
  }
  .when strong {
    color: var(--g-chrome);
    font-weight: 600;
  }
  .times {
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  h3 {
    margin: var(--g-space-4) 0 var(--g-space-2);
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
    font-weight: 400;
  }
  .nets {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: var(--g-space-1);
    max-height: 16rem;
    overflow: auto;
  }
  .nets li {
    display: flex;
    gap: var(--g-space-2);
    align-items: center;
  }
  .nets a {
    flex: 1;
    min-width: 0;
    display: grid;
    gap: 1px;
    padding: var(--g-space-2);
    border-radius: var(--g-radius-s);
    border: 1px solid transparent;
    background: rgb(255 255 255 / 0.02);
    color: var(--g-text);
    text-decoration: none;
  }
  .nets a:hover {
    border-color: var(--g-border-strong);
    background: var(--g-chrome-soft);
  }
  .name {
    font-size: var(--g-text-s);
  }
  .meta {
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  .live {
    color: var(--g-alert);
  }
  .muted {
    color: var(--g-text-muted);
    margin: 0 0 var(--g-space-2);
  }
  .warn {
    color: var(--g-warn);
    margin: var(--g-space-2) 0 0;
  }
  .small,
  .help {
    font-size: var(--g-text-xs);
  }
  .help {
    color: var(--g-text-muted);
    margin: 0;
  }
  code {
    color: var(--g-chrome);
  }
  @keyframes blink {
    to {
      opacity: 0.35;
    }
  }
</style>
