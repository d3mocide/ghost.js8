<script lang="ts">
  // Hero strip: where we are listening, what the situation is, and the few
  // numbers an operator glances at. Every figure comes from reported evidence.
  import { useApp } from '../../lib/state/context';
  import { situation } from '../../lib/state/situation';
  import { stationList } from '../../lib/state/state';
  import { bandFor } from '../../lib/bands';
  import { ago, formatMHz } from '../../lib/format';
  import Pill from '../../components/Pill.svelte';

  let { onSwitch }: { onSwitch: () => void } = $props();
  const app = useApp();
  const s = $derived(situation(app.state, app.now));
  const session = $derived(app.state.session);
  const dial = $derived(session?.tuning.dial_hz ?? null);
  const band = $derived(dial === null ? null : bandFor(dial));
  const lastHour = $derived(
    app.state.decodes.filter((d) => app.now - Date.parse(d.utc) < 3_600_000).length,
  );
  const heard = $derived(stationList(app.state).length);
  const lastDecode = $derived(app.state.health?.last_decode_utc ?? null);
</script>

<section class="hero {s.tone}" aria-label="Station overview">
  <div class="tuned">
    <span class="label">Listening on</span>
    <div class="freq-row">
      <span class="freq mono num" data-testid="dial"
        >{dial === null ? '— — —' : formatMHz(dial)}</span
      >
      <span class="unit">
        MHz
        {#if session}<span class="mode mono">{session.tuning.mode.toUpperCase()}</span>{/if}
        {#if band}<span class="band mono">{band}</span>{/if}
      </span>
    </div>
    <span class="rx" title={session?.receiver?.host}>
      {session?.receiver
        ? (session.receiver.name ?? session.receiver.host)
        : 'No receiver selected'}
    </span>
  </div>

  <div
    class="situation"
    data-testid="situation"
    data-code={s.code}
    role="status"
    aria-live="polite"
  >
    <Pill tone={s.tone} label={s.headline} />
    <p class:quiet={s.tone === 'ok'}>{s.detail}</p>
    {#if s.suggestSwitch}
      <button type="button" class="btn primary" onclick={onSwitch}>Choose receiver</button>
    {/if}
  </div>

  <dl class="stats">
    <div>
      <dt>Decodes · 1 h</dt>
      <dd class="mono num">{lastHour}</dd>
    </div>
    <div>
      <dt>Stations</dt>
      <dd class="mono num">{heard}</dd>
    </div>
    <div>
      <dt>Last decode</dt>
      <dd class="mono num">{lastDecode ? ago(lastDecode, app.now) : '—'}</dd>
    </div>
  </dl>
</section>

<style>
  .hero {
    position: relative;
    display: grid;
    grid-template-columns: minmax(16rem, auto) minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--g-space-5);
    padding: var(--g-space-4) var(--g-space-5);
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-l);
    background:
      radial-gradient(120% 160% at 0% 0%, rgb(103 232 249 / 0.1), transparent 50%),
      radial-gradient(120% 160% at 100% 100%, rgb(167 139 250 / 0.12), transparent 50%),
      var(--g-glass);
    box-shadow: var(--g-shadow), var(--g-inner-glow);
    backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
    -webkit-backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
  }
  .hero.alert {
    border-color: rgb(251 113 133 / 0.45);
  }
  .hero.warn {
    border-color: rgb(252 211 77 / 0.35);
  }
  .tuned {
    display: grid;
    gap: 2px;
    min-width: 0;
  }
  .label,
  dt {
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .freq-row {
    display: flex;
    align-items: baseline;
    gap: var(--g-space-2);
  }
  .freq {
    font-family: var(--g-font-display);
    font-size: 2.6rem;
    font-weight: 400;
    line-height: 1.05;
    letter-spacing: 0;
    background: var(--g-accent);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    filter: drop-shadow(0 0 18px rgb(125 211 252 / 0.25));
  }
  .unit {
    display: inline-flex;
    align-items: baseline;
    gap: 6px;
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
  }
  .mode,
  .band {
    padding: 1px 6px;
    border-radius: var(--g-radius-pill);
    background: var(--g-glass-raised);
    border: 1px solid var(--g-border);
    color: var(--g-text);
    font-size: 10.5px;
  }
  .rx {
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .situation {
    display: flex;
    align-items: center;
    gap: var(--g-space-3);
    flex-wrap: wrap;
    min-width: 0;
    padding-left: var(--g-space-5);
    border-left: 1px solid var(--g-border);
  }
  .situation p {
    margin: 0;
    flex: 1 1 14rem;
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
  }
  .stats {
    display: flex;
    gap: var(--g-space-2);
    margin: 0;
  }
  .stats div {
    min-width: 6.5rem;
    padding: var(--g-space-2) var(--g-space-3);
    border-radius: var(--g-radius-m);
    background: var(--g-glass-raised);
    border: 1px solid var(--g-hairline);
  }
  dd {
    margin: 2px 0 0;
    font-size: var(--g-text-l);
    font-weight: 600;
    color: var(--g-text);
  }
  @media (max-width: 1280px) {
    .hero {
      grid-template-columns: minmax(0, 1fr) auto;
    }
    .situation {
      grid-column: 1 / -1;
      grid-row: 2;
      padding-left: 0;
      border-left: 0;
    }
  }
  @media (max-width: 720px) {
    .hero {
      grid-template-columns: minmax(0, 1fr);
      gap: var(--g-space-3);
      padding: var(--g-space-4);
    }
    .situation {
      grid-row: auto;
    }
    .freq {
      font-size: var(--g-text-xl);
    }
    .stats div {
      flex: 1;
      min-width: 0;
      padding: var(--g-space-2);
    }
    .stats dt {
      font-size: 10px;
      letter-spacing: 0.03em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    /* Healthy state: the headline pill says it all; keep prose for warnings. */
    .situation p.quiet {
      display: none;
    }
    .situation {
      gap: var(--g-space-2);
    }
  }
</style>
