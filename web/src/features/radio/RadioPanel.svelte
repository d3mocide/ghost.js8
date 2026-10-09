<script lang="ts">
  // One strip for everything that shapes what you hear: dial, band, mode, passband
  // and the browser audio monitor. Tuning is shared by everyone watching the station.
  import { onDestroy } from 'svelte';
  import Panel from '../../components/Panel.svelte';
  import Pill from '../../components/Pill.svelte';
  import { useApp } from '../../lib/state/context';
  import { JS8_BANDS } from '../../lib/bands';
  import { formatMHz } from '../../lib/format';
  import type { TuningModel } from '../../lib/protocol/generated';

  const app = useApp();
  const tuning = $derived<TuningModel>(
    app.state.session?.tuning ?? {
      dial_hz: 14_078_000,
      mode: 'usb',
      low_cut_hz: 100,
      high_cut_hz: 3000,
    },
  );

  const PASSBANDS = [
    { label: 'JS8', low: 100, high: 3000, hint: '100–3000 Hz: the whole JS8 slot' },
    { label: 'Narrow', low: 200, high: 2500, hint: '200–2500 Hz: less noise, fewer edge signals' },
    { label: 'Wide', low: 50, high: 4000, hint: '50–4000 Hz: everything the receiver passes' },
  ] as const;

  let dialKHz = $state('');
  let editing = $state(false);
  let low = $state(100);
  let high = $state(3000);
  let error = $state<string | null>(null);

  // Follow the shared session (another viewer may retune) unless the dial is being typed.
  $effect(() => {
    if (!editing && pendingHz === null) dialKHz = fmtKHz(tuning.dial_hz);
    low = tuning.low_cut_hz;
    high = tuning.high_cut_hz;
  });

  const fmtKHz = (hz: number): string => (hz / 1000).toFixed(3);

  function tune(next: Partial<TuningModel>): void {
    const t: TuningModel = { ...tuning, ...next };
    if (!(t.low_cut_hz >= 0 && t.high_cut_hz <= 6000 && t.low_cut_hz < t.high_cut_hz)) {
      error = 'Passband must satisfy 0 ≤ low < high ≤ 6000 Hz.';
      return;
    }
    if (!(t.dial_hz > 0 && t.dial_hz < 100_000_000)) {
      error = 'Dial frequency out of range.';
      return;
    }
    error = null;
    app.send({ v: 1, type: 'tune', tuning: t });
  }

  // Stepping is debounced so holding a key sends one tune, not a burst the bridge would throttle.
  let pendingHz: number | null = $state(null);
  let timer: ReturnType<typeof setTimeout> | undefined;
  function nudge(deltaHz: number): void {
    const base = pendingHz ?? tuning.dial_hz;
    pendingHz = Math.min(99_999_000, Math.max(1_000, base + deltaHz));
    dialKHz = fmtKHz(pendingHz);
    clearTimeout(timer);
    timer = setTimeout(() => {
      const hz = pendingHz;
      pendingHz = null;
      if (hz !== null) tune({ dial_hz: hz });
    }, 250);
  }
  onDestroy(() => {
    clearTimeout(timer);
  });

  function commitDial(): void {
    editing = false;
    const hz = Math.round(Number(dialKHz) * 1000);
    if (!Number.isFinite(hz) || dialKHz.trim() === '') {
      error = 'Enter the dial frequency in kHz, e.g. 14078.000';
      dialKHz = fmtKHz(tuning.dial_hz);
      return;
    }
    if (hz !== tuning.dial_hz) tune({ dial_hz: hz });
  }

  function dialKey(e: KeyboardEvent): void {
    const step = e.shiftKey ? 1000 : e.altKey ? 10 : 100;
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      nudge(step);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      nudge(-step);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      commitDial();
    } else if (e.key === 'Escape') {
      editing = false;
      dialKHz = fmtKHz(tuning.dial_hz);
    }
  }

  // Audio monitor. Worklet counters are samples at 12 kHz; the panel reports time.
  const fresh = $derived(app.state.lastAudioAt !== null && app.now - app.state.lastAudioAt < 3000);
  const toMs = (samples: number): number => Math.round((samples / 12_000) * 1000);
  const bufferedMs = $derived(app.audioStats ? toMs(app.audioStats.buffered) : null);
  const droppedMs = $derived(app.audioStats ? toMs(app.audioStats.dropped) : null);
  const silentMs = $derived(app.audioStats ? toMs(app.audioStats.underruns) : null);
  // Only report what is wrong: dropped or silent audio appears once it has happened.
  const statsText = $derived(
    bufferedMs === null
      ? ''
      : [
          `buffer ${String(bufferedMs)} ms`,
          droppedMs ? `dropped ${String(droppedMs)} ms` : null,
          silentMs ? `silent ${String(silentMs)} ms` : null,
        ]
          .filter((x) => x !== null)
          .join(' · '),
  );
</script>

<Panel id="radio" code="RADIO" title="Radio" slim>
  <div class="radio">
    <div class="tune">
      <div class="line">
        <div class="dial" role="group" aria-label="Dial frequency">
          <button
            type="button"
            class="step"
            aria-label="Down 1 kilohertz"
            title="−1 kHz"
            onclick={() => {
              nudge(-1000);
            }}>«</button
          >
          <button
            type="button"
            class="step"
            aria-label="Down 100 hertz"
            title="−100 Hz"
            onclick={() => {
              nudge(-100);
            }}>‹</button
          >
          <label class="freq">
            <span class="sr-only">Dial (kHz)</span>
            <input
              class="input mono"
              inputmode="decimal"
              spellcheck="false"
              autocomplete="off"
              bind:value={dialKHz}
              onfocus={() => (editing = true)}
              onblur={commitDial}
              onkeydown={dialKey}
              aria-describedby="radio-help"
            />
            <span class="unit">kHz</span>
          </label>
          <button
            type="button"
            class="step"
            aria-label="Up 100 hertz"
            title="+100 Hz"
            onclick={() => {
              nudge(100);
            }}>›</button
          >
          <button
            type="button"
            class="step"
            aria-label="Up 1 kilohertz"
            title="+1 kHz"
            onclick={() => {
              nudge(1000);
            }}>»</button
          >
        </div>

        <div class="seg" role="group" aria-label="Mode">
          {#each ['usb', 'lsb'] as const as m (m)}
            <button
              type="button"
              aria-pressed={tuning.mode === m}
              onclick={() => {
                tune({ mode: m });
              }}>{m.toUpperCase()}</button
            >
          {/each}
        </div>

        <div class="pass">
          <div class="seg" role="group" aria-label="Passband">
            {#each PASSBANDS as p (p.label)}
              <button
                type="button"
                title={p.hint}
                aria-pressed={tuning.low_cut_hz === p.low && tuning.high_cut_hz === p.high}
                onclick={() => {
                  tune({ low_cut_hz: p.low, high_cut_hz: p.high });
                }}>{p.label}</button
              >
            {/each}
          </div>

          <details class="custom">
            <summary title="Custom passband">±</summary>
            <form
              onsubmit={(e) => {
                e.preventDefault();
                tune({ low_cut_hz: low, high_cut_hz: high });
              }}
            >
              <label class="field"
                >Low (Hz)
                <input
                  class="input cut"
                  type="number"
                  min="0"
                  max="6000"
                  step="50"
                  bind:value={low}
                /></label
              >
              <label class="field"
                >High (Hz)
                <input
                  class="input cut"
                  type="number"
                  min="0"
                  max="6000"
                  step="50"
                  bind:value={high}
                /></label
              >
              <button type="submit" class="btn primary">Set</button>
            </form>
          </details>
        </div>
      </div>
      <div class="bands" role="group" aria-label="JS8 band presets">
        {#each JS8_BANDS as b (b.band)}
          <button
            type="button"
            class="btn"
            aria-pressed={tuning.dial_hz === b.dialHz}
            title={`${formatMHz(b.dialHz)} MHz${b.dialHz > 32_000_000 ? ' (beyond most KiwiSDRs)' : ''}`}
            onclick={() => {
              tune({ dial_hz: b.dialHz, mode: 'usb' });
            }}>{b.band}</button
          >
        {/each}
      </div>
    </div>

    <div class="audio" data-testid="panel-audio">
      <div class="line audio-row">
        {#if app.audioEnabled}
          <button
            type="button"
            class="btn"
            onclick={() => app.disableAudio()}
            data-testid="audio-toggle">Stop audio</button
          >
        {:else}
          <button
            type="button"
            class="btn primary"
            onclick={() => app.enableAudio()}
            data-testid="audio-toggle">Enable audio</button
          >
        {/if}
        <label class="vol">
          <span class="sr-only">Volume</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={app.volume}
            oninput={(e) => {
              app.setVolume(Number(e.currentTarget.value));
            }}
          />
          <span class="mono num">{Math.round(app.volume * 100)}%</span>
        </label>
      </div>
      {#if app.audioError}<p class="error" role="alert">
          Audio could not start: {app.audioError}
        </p>{/if}
      {#if app.audioEnabled}
        <p class="stats mono">
          <Pill tone={fresh ? 'ok' : 'warn'} label={fresh ? 'live' : 'no audio'} />
          {#if statsText}{statsText}{/if}
        </p>
      {/if}
    </div>
  </div>
  <p id="radio-help" class="sr-only">
    Tuning is shared by everyone watching this station. JS8 lives at the dial plus 0 to 3 kilohertz
    (USB). Up and down arrows step 100 hertz, with shift 1 kilohertz. Audio monitoring changes what
    you hear, not what the decoder receives.
  </p>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</Panel>

<style>
  /* A column card: dial, mode and passband on top, bands, then the audio monitor. */
  .radio {
    display: grid;
    gap: var(--g-space-4);
  }
  .tune {
    min-width: 0;
    display: grid;
    gap: var(--g-space-3);
  }
  .pass {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .audio {
    display: grid;
    gap: var(--g-space-2);
    padding-top: var(--g-space-4);
    border-top: 1px solid var(--g-hairline);
  }
  .line {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--g-space-2);
  }
  .dial {
    display: flex;
    width: 100%;
    align-items: center;
    gap: 4px;
  }
  .step {
    width: 30px;
    height: 38px;
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-m);
    background: var(--g-glass-raised);
    color: var(--g-text);
    font-size: 1.1rem;
    line-height: 1;
    cursor: pointer;
    transition: background var(--g-dur-fast) var(--g-ease);
  }
  .step:hover {
    background: var(--g-accent-soft);
  }
  .freq {
    position: relative;
    display: inline-flex;
    flex: 1;
    align-items: center;
  }
  .freq input {
    width: 100%;
    padding-right: 2.6rem;
    font-size: 1.15rem;
    font-weight: 600;
    text-align: right;
    letter-spacing: 0.02em;
  }
  .unit {
    position: absolute;
    right: 10px;
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
    pointer-events: none;
  }
  .seg {
    display: inline-flex;
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-pill);
    overflow: hidden;
  }
  .seg button {
    min-height: 34px;
    padding: 0 10px;
    border: 0;
    background: transparent;
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
    font-weight: 600;
    cursor: pointer;
  }
  .seg button + button {
    border-left: 1px solid var(--g-hairline);
  }
  .seg button[aria-pressed='true'] {
    background: var(--g-accent-soft);
    color: var(--g-text);
  }
  .custom summary {
    cursor: pointer;
    list-style: none;
    width: 30px;
    height: 30px;
    display: grid;
    place-items: center;
    border: 1px solid var(--g-border);
    border-radius: 50%;
    color: var(--g-chrome);
  }
  .custom summary::-webkit-details-marker {
    display: none;
  }
  .custom[open] summary {
    background: var(--g-accent-soft);
  }
  .custom form {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: var(--g-space-2);
    margin-top: var(--g-space-2);
  }
  .cut {
    width: 5.5rem;
  }
  .bands {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .bands .btn {
    min-height: 30px;
    min-width: 3.1rem;
    padding: 0 8px;
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    font-weight: 600;
  }
  .audio-row {
    flex-wrap: nowrap;
  }
  .audio-row .btn {
    flex: none;
  }
  .vol {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: var(--g-space-2);
  }
  .vol input {
    flex: 1;
    min-width: 3rem;
  }
  .vol .num {
    width: 3ch;
    text-align: right;
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  .stats {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--g-space-2);
    margin: 0;
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  .error {
    margin: var(--g-space-2) 0 0;
    color: var(--g-alert);
    font-size: var(--g-text-s);
  }
  @media (max-width: 720px) {
    .bands {
      flex-wrap: nowrap;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .bands .btn {
      flex: none;
    }
  }
</style>
