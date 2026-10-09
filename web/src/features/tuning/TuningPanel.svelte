<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import { useApp } from '../../lib/state/context';
  import { bandFor, JS8_BANDS } from '../../lib/bands';
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
  let dialKHz = $state('');
  let low = $state(100);
  let high = $state(3000);
  let mode = $state<'usb' | 'lsb'>('usb');
  let error = $state<string | null>(null);

  // Follow the shared session (another viewer may retune).
  $effect(() => {
    dialKHz = (tuning.dial_hz / 1000).toFixed(3);
    low = tuning.low_cut_hz;
    high = tuning.high_cut_hz;
    mode = tuning.mode;
  });

  function tune(next: Partial<TuningModel>): void {
    const t: TuningModel = {
      dial_hz: tuning.dial_hz,
      mode,
      low_cut_hz: low,
      high_cut_hz: high,
      ...next,
    };
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

  function submit(ev: SubmitEvent): void {
    ev.preventDefault();
    const hz = Math.round(Number(dialKHz) * 1000);
    if (!Number.isFinite(hz)) {
      error = 'Enter the dial frequency in kHz, e.g. 14078.000';
      return;
    }
    tune({ dial_hz: hz });
  }
</script>

<Panel id="tuning" code="TUNE" title="Tuning" slim>
  <div class="strip">
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

    <form onsubmit={submit} class="manual" aria-describedby="tune-help">
      <label class="field"
        >Dial (kHz)
        <input
          class="input dial"
          inputmode="decimal"
          bind:value={dialKHz}
          aria-describedby="tune-help"
        />
      </label>
      <fieldset class="mode">
        <legend class="field">Mode</legend>
        <label><input type="radio" bind:group={mode} value="usb" /> USB</label>
        <label><input type="radio" bind:group={mode} value="lsb" /> LSB</label>
      </fieldset>
      <label class="field"
        >Low (Hz) <input
          class="input cut"
          type="number"
          min="0"
          max="6000"
          step="50"
          bind:value={low}
        /></label
      >
      <label class="field"
        >High (Hz) <input
          class="input cut"
          type="number"
          min="0"
          max="6000"
          step="50"
          bind:value={high}
        /></label
      >
      <button type="submit" class="btn primary">Apply</button>
    </form>
    {#if bandFor(tuning.dial_hz)}<span class="band mono">{bandFor(tuning.dial_hz)}</span>{/if}
  </div>
  <p id="tune-help" class="help">
    Tuning is shared by everyone watching this station. JS8 lives at the dial + 0–3 kHz (USB).
  </p>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</Panel>

<style>
  .strip {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: var(--g-space-3) var(--g-space-4);
  }
  .band {
    padding: 2px 8px;
    border-radius: var(--g-radius-pill);
    background: var(--g-accent-soft);
    color: var(--g-text);
    font-size: var(--g-text-xs);
    align-self: center;
  }
  .bands {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .bands .btn {
    min-height: 32px;
    min-width: 3.2rem;
    padding: 0 6px;
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    font-weight: 600;
  }
  .manual {
    display: flex;
    flex-wrap: wrap;
    gap: var(--g-space-3);
    align-items: end;
  }
  .dial {
    width: 8.5rem;
  }
  .cut {
    width: 5.5rem;
  }
  .mode {
    border: 0;
    padding: 0;
    margin: 0;
    display: flex;
    gap: var(--g-space-3);
    align-items: center;
    min-height: 38px;
    font-size: var(--g-text-s);
  }
  .mode legend {
    float: left;
    margin-right: var(--g-space-1);
  }
  .mode label {
    display: inline-flex;
    align-items: center;
    gap: var(--g-space-1);
    white-space: nowrap;
  }
  @media (max-width: 720px) {
    .strip {
      gap: var(--g-space-3);
    }
    .bands {
      flex-wrap: nowrap;
      overflow-x: auto;
      width: 100%;
      padding-bottom: 2px;
      scrollbar-width: none;
    }
    .bands .btn {
      flex: none;
    }
    .manual {
      width: 100%;
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      align-items: end;
    }
    .manual .dial,
    .manual .cut {
      width: 100%;
    }
    .manual :global(.field:first-child) {
      grid-column: 1 / 3;
    }
    .mode {
      grid-column: 3;
      flex-direction: column;
      align-items: flex-start;
      gap: 0;
      min-height: 0;
    }
    .mode legend {
      float: none;
    }
    .manual .btn.primary {
      width: 100%;
    }
    .band {
      display: none; /* the hero already shows the band */
    }
  }
  .help {
    /* Kept for assistive tech; the strip stays one row. */
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    margin: 0;
  }
  .error {
    color: var(--g-alert);
    font-size: var(--g-text-s);
    margin: var(--g-space-2) 0 0;
  }
</style>
