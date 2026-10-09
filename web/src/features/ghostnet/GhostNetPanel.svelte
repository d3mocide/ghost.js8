<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import Pill from '../../components/Pill.svelte';
  import type { PillTone } from '../../components/pill';
  import { useApp } from '../../lib/state/context';
  import { countdown, localWhen, REGION_LABEL } from '../../lib/ghostnet';
  import { formatMHz, utcDateTime, utcTime } from '../../lib/format';
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
  // How far through the window we are, 0..1 (only meaningful while it is under way).
  const progress = $derived.by(() => {
    if (!target || !inWindow || !started) return 0;
    const a = Date.parse(target.start);
    const b = Date.parse(target.end);
    return b > a ? Math.min(1, Math.max(0, (app.now - a) / (b - a))) : 0;
  });
  const countLabel = $derived(
    inWindow && started ? 'left on air' : inWindow ? 'pre-roll, on air in' : 'until next net',
  );
  const hhmm = (iso: string): string => `${utcTime(iso, false)}Z`;
  // "nearest free receiver: 283 km, SNR 26 dB" -> "283 km away, SNR 26 dB"
  const receiverNote = $derived(
    (g?.receiver_reason ?? '')
      .replace(/^nearest free receiver:\s*/i, '')
      .replace(/ km,/, ' km away,'),
  );
  const manual = $derived(g?.mode === 'paused');

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
          {#if g.recording_net_id}<span class="rec" role="img" aria-label="recording"
              ><span class="dot" aria-hidden="true"></span>REC</span
            >{/if}
          <span class="name">{target.label}</span>
        </div>
        <div class="freq mono">
          <span class="band">{target.band}</span>
          {formatMHz(target.dial_hz)} MHz USB
        </div>
        <div class="count">
          <strong class="mono">
            {#if inWindow && started}
              {countdown(app.now, Date.parse(target.end))}
            {:else}
              {countdown(app.now, Date.parse(target.start))}
            {/if}
          </strong>
          <span class="count-label">{countLabel}</span>
        </div>
        {#if inWindow && started}
          <div
            class="bar"
            role="progressbar"
            aria-label="Time into the net"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow={Math.round(progress * 100)}
          >
            <span style:width={`${String(progress * 100)}%`}></span>
          </div>
        {/if}
        <div class="times mono">
          {hhmm(target.start)} – {hhmm(target.end)} · {localWhen(target.start)} local
        </div>
      </div>
    {/if}

    {#if manual}
      <p class="notice">
        <span aria-hidden="true">⏸</span>
        <span
          >Manual control{#if g.paused_until}. Autopilot resumes <strong class="mono"
              >{hhmm(g.paused_until)}</strong
            >{/if}</span
        >
      </p>
    {:else}
      {#if receiverNote}<p class="muted small">Receiver: {receiverNote}</p>{/if}
      {#if g.detail}<p class="warn small">{g.detail}</p>{/if}
    {/if}
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
              <span>{utcDateTime(n.scheduled_start).slice(5, 16)}Z</span>
              <span>{n.decode_count} decodes</span>
              <span>{n.station_count} stations</span>
            </span>
          </a>
          {#if n.ended === null}<Pill tone="alert" label="rec" />{/if}
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
    padding: var(--g-space-3);
    border: 1px solid var(--g-hairline);
    border-radius: var(--g-radius-m);
    background:
      radial-gradient(120% 140% at 100% 0%, rgb(167 139 250 / 0.14), transparent 60%),
      var(--g-glass-raised);
  }
  .window.live {
    border-color: rgb(94 234 212 / 0.4);
    box-shadow: 0 0 24px -6px rgb(94 234 212 / 0.35);
  }
  .label {
    display: flex;
    gap: var(--g-space-2);
    align-items: center;
    min-width: 0;
  }
  .label .name {
    font-size: var(--g-text-m);
    font-weight: 600;
    min-width: 0;
  }
  .rec {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 1px 8px 1px 6px;
    border-radius: var(--g-radius-pill);
    border: 1px solid rgb(251 113 133 / 0.4);
    background: rgb(251 113 133 / 0.12);
    color: var(--g-alert);
    font-family: var(--g-font-mono);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.1em;
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--g-alert);
    box-shadow: 0 0 8px var(--g-alert);
    animation: pulse 1.6s ease-in-out infinite;
  }
  .freq {
    display: flex;
    align-items: center;
    gap: var(--g-space-2);
    color: var(--g-signal);
    font-size: var(--g-text-s);
  }
  .band {
    padding: 0 7px;
    border-radius: var(--g-radius-pill);
    background: var(--g-accent-soft);
    color: var(--g-text);
    font-size: var(--g-text-xs);
  }
  .count {
    display: flex;
    align-items: baseline;
    gap: var(--g-space-2);
    margin-top: var(--g-space-2);
  }
  .count strong {
    font-size: 1.6rem;
    font-weight: 600;
    line-height: 1.1;
    background: var(--g-accent);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
  .count-label {
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
  }
  .bar {
    height: 4px;
    margin-top: var(--g-space-2);
    border-radius: 2px;
    background: var(--g-hairline);
    overflow: hidden;
  }
  .bar span {
    display: block;
    height: 100%;
    background: var(--g-accent);
    border-radius: 2px;
    transition: width 1s linear;
  }
  .times {
    margin-top: var(--g-space-2);
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  .notice {
    display: flex;
    gap: var(--g-space-2);
    align-items: baseline;
    margin: var(--g-space-3) 0 0;
    padding: var(--g-space-2) var(--g-space-3);
    border-radius: var(--g-radius-m);
    border: 1px solid rgb(252 211 77 / 0.25);
    background: rgb(252 211 77 / 0.07);
    color: var(--g-warn);
    font-size: var(--g-text-xs);
  }
  h3 {
    margin: var(--g-space-4) 0 var(--g-space-2);
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
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
    padding: var(--g-space-2) var(--g-space-3);
    border-radius: var(--g-radius-m);
    border: 1px solid var(--g-hairline);
    background: var(--g-glass-raised);
    color: var(--g-text);
    text-decoration: none;
    transition:
      background var(--g-dur-fast) var(--g-ease),
      border-color var(--g-dur-fast) var(--g-ease);
  }
  .nets a:hover {
    border-color: var(--g-border-strong);
    background: rgb(255 255 255 / 0.09);
  }
  .nets .name {
    font-size: var(--g-text-s);
    font-weight: 600;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0 var(--g-space-3);
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  .meta span {
    white-space: nowrap;
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
  @keyframes pulse {
    50% {
      opacity: 0.35;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .dot {
      animation: none;
    }
    .bar span {
      transition: none;
    }
  }
</style>
