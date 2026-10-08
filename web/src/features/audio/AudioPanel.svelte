<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import Pill from '../../components/Pill.svelte';
  import { useApp } from '../../lib/state/context';

  const app = useApp();
  const fresh = $derived(app.state.lastAudioAt !== null && app.now - app.state.lastAudioAt < 3000);
  const bufferedMs = $derived(
    app.audioStats ? Math.round((app.audioStats.buffered / 12_000) * 1000) : null,
  );
</script>

<Panel id="audio" code="AUD" title="Audio monitor">
  {#snippet actions()}
    {#if app.audioEnabled}
      <Pill tone={fresh ? 'ok' : 'warn'} label={fresh ? 'live' : 'no audio'} />
    {/if}
  {/snippet}
  <div class="row">
    {#if app.audioEnabled}
      <button
        type="button"
        class="btn"
        onclick={() => app.disableAudio()}
        data-testid="audio-toggle">Stop audio</button
      >
      <button
        type="button"
        class="btn"
        aria-pressed={app.muted}
        onclick={() => {
          app.setMuted(!app.muted);
        }}
      >
        {app.muted ? 'Muted' : 'Mute'}
      </button>
    {:else}
      <button type="button" class="btn" onclick={() => app.enableAudio()} data-testid="audio-toggle"
        >Enable audio</button
      >
    {/if}
  </div>
  <label class="field volume">
    Volume <span class="mono num">{Math.round(app.volume * 100)}%</span>
    <input
      type="range"
      min="0"
      max="1"
      step="0.01"
      value={app.volume}
      oninput={(e) => {
        app.setVolume(Number(e.currentTarget.value));
      }}
      disabled={!app.audioEnabled}
    />
  </label>
  {#if app.audioError}<p class="error" role="alert">Audio could not start: {app.audioError}</p>{/if}
  {#if app.audioEnabled && app.audioStats}
    <p class="stats mono">
      buffer {bufferedMs} ms · dropped {app.audioStats.dropped} · gaps {app.audioStats.underruns}
    </p>
  {/if}
  <p class="help">Monitoring only. Volume changes what you hear, not what the decoder receives.</p>
</Panel>

<style>
  .row {
    display: flex;
    gap: var(--g-space-2);
    flex-wrap: wrap;
  }
  .volume {
    margin-top: var(--g-space-3);
  }
  .volume input {
    width: 100%;
    accent-color: var(--g-signal);
  }
  .stats,
  .help {
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
    margin: var(--g-space-2) 0 0;
  }
  .error {
    color: var(--g-alert);
    font-size: var(--g-text-s);
  }
</style>
