<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import { useApp } from '../../lib/state/context';
  import { formatSnr, utcTime } from '../../lib/format';
  import { classify } from '../../lib/ghostnet';

  const app = useApp();
  let directedOnly = $state(false);
  const rows = $derived(
    [...app.state.decodes].reverse().filter((d) => !directedOnly || d.kind === 'directed'),
  );

  // Throttled screen-reader announcements: at most one every 10 s.
  let announcement = $state('');
  let lastAnnounced = 0;
  let pending = 0;
  let seen = 0;
  $effect(() => {
    const total = app.state.decodes.length;
    const latest = app.state.decodes.at(-1);
    if (total > seen && latest) pending += total - seen;
    seen = total;
    if (pending > 0 && latest && Date.now() - lastAnnounced > 10_000) {
      announcement = `${String(pending)} new decode${pending > 1 ? 's' : ''}. Latest: ${latest.text}`;
      pending = 0;
      lastAnnounced = Date.now();
    }
  });
</script>

<Panel id="timeline" code="TRF" title="Decoded traffic" flush>
  {#snippet actions()}
    <button
      type="button"
      class="btn ghost"
      aria-pressed={directedOnly}
      onclick={() => (directedOnly = !directedOnly)}
    >
      Directed
    </button>
  {/snippet}
  <div class="sr-only" aria-live="polite" aria-atomic="true">{announcement}</div>
  {#if rows.length === 0}
    <p class="empty">
      No traffic copied yet. Decodes appear here every 15-second cycle when JS8 is heard.
    </p>
  {:else}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex (scrollable region must be keyboard-reachable) -->
    <ol class="list" data-testid="timeline" tabindex="0" aria-label="Decoded traffic, newest first">
      {#each rows as d (d.key)}
        {@const tags = classify(d.text)}
        <li
          class="row {d.kind}"
          class:flash={tags.flash}
          class:gn={tags.ghostnet}
          data-testid="decode-row"
        >
          <time class="t mono" datetime={d.utc}>{utcTime(d.utc)}Z</time>
          <span class="snr mono num" title="Signal-to-noise ratio, dB">{formatSnr(d.snr_db)}</span>
          <span class="off mono num" title="Audio offset, Hz">{d.offset_hz}</span>
          <span class="kind" title={d.kind === 'directed' ? 'Directed message' : 'Activity'}>
            {#if d.kind === 'directed'}<span aria-hidden="true">➤</span> DIR{:else}<span
                aria-hidden="true">·</span
              > ACT{/if}
          </span>
          <span class="text mono"
            >{#if tags.flash}<span class="tag alert">FLASH</span>{/if}{#if tags.ghostnet}<span
                class="tag gn">{tags.regional ?? 'GN'}</span
              >{/if}{d.text}</span
          >
        </li>
      {/each}
    </ol>
  {/if}
</Panel>

<style>
  .empty {
    margin: 0;
    padding: var(--g-space-4);
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: clamp(220px, 40vh, 560px);
    overflow: auto;
  }
  .row {
    display: grid;
    grid-template-columns: 5.4rem 3rem 3.4rem 3.6rem 1fr;
    gap: var(--g-space-2);
    align-items: baseline;
    padding: 6px var(--g-space-3);
    border-bottom: 1px solid rgb(92 225 255 / 0.06);
    font-size: var(--g-text-s);
    animation: acquire var(--g-dur-slow) var(--g-ease);
  }
  .row.directed {
    background: linear-gradient(90deg, rgb(61 255 154 / 0.07), transparent 40%);
  }
  .row.gn {
    background: linear-gradient(90deg, rgb(92 225 255 / 0.08), transparent 45%);
  }
  .row.flash {
    background: linear-gradient(90deg, rgb(255 77 94 / 0.2), transparent 60%);
  }
  .tag {
    display: inline-block;
    margin-right: 6px;
    padding: 0 4px;
    border: 1px solid currentColor;
    border-radius: 3px;
    font-size: 10px;
    vertical-align: 1px;
  }
  .tag.alert {
    color: var(--g-alert);
  }
  .tag.gn {
    color: var(--g-chrome);
  }
  .t,
  .off {
    color: var(--g-text-muted);
  }
  .snr {
    color: var(--g-chrome);
    text-align: right;
  }
  .off {
    text-align: right;
  }
  .kind {
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    letter-spacing: 0.08em;
    color: var(--g-text-muted);
  }
  .directed .kind {
    color: var(--g-signal);
  }
  .text {
    color: var(--g-text);
    overflow-wrap: anywhere;
  }
  @keyframes acquire {
    from {
      background-color: rgb(61 255 154 / 0.22);
      filter: blur(1px);
    }
    to {
      filter: none;
    }
  }
  @media (max-width: 720px) {
    .row {
      grid-template-columns: 5rem 2.6rem 3rem 1fr;
    }
    .kind {
      display: none;
    }
  }
</style>
