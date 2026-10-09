<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import { useApp } from '../../lib/state/context';
  import { formatSnr, utcTime } from '../../lib/format';
  import { classify } from '../../lib/ghostnet';
  import { groupThreads } from '../../lib/state/threads';
  import { selection } from '../../lib/state/selection.svelte';
  import { isNoiseFrame, speedChip } from '../../lib/traffic';
  import { loadTrafficPrefs, saveTrafficPrefs } from '../../lib/traffic-prefs';

  const app = useApp();
  const prefs = loadTrafficPrefs();
  let directedOnly = $state(prefs.directedOnly);
  let threaded = $state(prefs.threaded);
  $effect(() => {
    saveTrafficPrefs({ directedOnly, threaded });
  });
  const rows = $derived(
    [...app.state.decodes]
      .reverse()
      // Frames the decoder heard but could not read (just "…") are noise in the list.
      .filter((d) => !(d.kind === 'activity' && isNoiseFrame(d.text)))
      .filter((d) => !directedOnly || d.kind === 'directed'),
  );
  // Threads stitch each station's activity frames (same audio offset, one per slot).
  const threads = $derived(
    threaded
      ? groupThreads(app.state.decodes).filter(
          (i) => !directedOnly || (i.kind === 'single' && i.row.kind === 'directed'),
        )
      : [],
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
      aria-pressed={threaded}
      title="Join each station's frames into one running line"
      onclick={() => (threaded = !threaded)}
    >
      Threads
    </button>
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
  {:else if threaded}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex (scrollable region must be keyboard-reachable) -->
    <ol
      class="list"
      data-testid="timeline"
      tabindex="0"
      aria-label="Traffic by station, newest first"
    >
      {#each threads as item (item.key)}
        {#if item.kind === 'thread'}
          {@const tags = classify(item.text)}
          <li
            class="row"
            class:flash={tags.flash}
            class:gn={tags.ghostnet}
            data-testid="thread-row"
          >
            <time class="t mono" datetime={item.lastUtc}>{utcTime(item.lastUtc)}Z</time>
            <span class="snr mono num" title="Latest SNR, dB">{formatSnr(item.snr_db)}</span>
            <span class="off mono num" title="Audio offset, Hz">{item.offset_hz}</span>
            <span class="kind">
              <span
                class="chip act"
                title={`${String(item.frames)} frame${item.frames === 1 ? '' : 's'}${item.gaps ? `, ${String(item.gaps)} missed` : ''}`}
                >×{item.frames}</span
              >
            </span>
            <span class="text mono"
              >{#if tags.flash}<span class="chip alert">FLASH</span>{/if}{#if tags.ghostnet}<span
                  class="chip gn">{tags.regional ?? 'GN'}</span
                >{/if}{item.text}</span
            >
          </li>
        {:else if item.kind === 'single'}
          {@const d = item.row}
          <li class="row {d.kind}" data-testid="decode-row">
            <time class="t mono" datetime={d.utc}>{utcTime(d.utc)}Z</time>
            <span class="snr mono num">{formatSnr(d.snr_db)}</span>
            <span class="off mono num">{d.offset_hz}</span>
            <span class="kind"><span class="chip dir">DIR</span></span>
            <span class="text mono">{d.text}</span>
          </li>
        {/if}
      {/each}
    </ol>
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
            {#if d.kind === 'directed'}<span class="chip dir">DIR</span>{:else}<span
                class="chip act">ACT</span
              >{/if}
          </span>
          <span class="text mono"
            >{#if tags.flash}<span class="chip alert">FLASH</span>{/if}{#if tags.ghostnet}<span
                class="chip gn">{tags.regional ?? 'GN'}</span
              >{/if}{#if speedChip(d.speed)}<span class="chip spd" title={`JS8 ${d.speed} speed`}
                >{speedChip(d.speed)}</span
              >{/if}{#if d.from_call && d.text.startsWith(`${d.from_call}:`)}<button
                type="button"
                class="from"
                title={`History for ${d.from_call}`}
                onclick={() => {
                  if (d.from_call) selection.open(d.from_call);
                }}>{d.from_call}</button
              >{d.text.slice(d.from_call.length)}{:else}{d.text}{/if}</span
          >
        </li>
      {/each}
    </ol>
  {/if}
</Panel>

<style>
  .empty {
    margin: 0;
    padding: var(--g-space-5) var(--g-space-4);
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
    text-align: center;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: var(--g-space-1) 0;
    /* Phone: cap the list so the tab stays short. Wide layouts stretch the panel instead. */
    max-height: clamp(240px, 42vh, 600px);
    overflow: auto;
  }
  @media (min-width: 1281px) {
    .list {
      max-height: none;
    }
  }
  .row {
    position: relative;
    display: grid;
    grid-template-columns: 5.4rem 2.8rem 3.2rem 3.2rem 1fr;
    gap: var(--g-space-2);
    align-items: baseline;
    padding: 7px var(--g-space-4);
    font-size: var(--g-text-s);
    animation: acquire var(--g-dur-slow) var(--g-ease);
    transition: background var(--g-dur-fast) var(--g-ease);
  }
  .row + .row {
    border-top: 1px solid var(--g-hairline);
  }
  .row:hover {
    background: var(--g-glass-raised);
  }
  .row::before {
    /* category rail */
    content: '';
    position: absolute;
    left: 0;
    top: 6px;
    bottom: 6px;
    width: 2px;
    border-radius: 2px;
    background: transparent;
  }
  .row.directed::before {
    background: var(--g-signal);
    opacity: 0.6;
  }
  .row.gn::before {
    background: var(--g-violet);
  }
  .row.flash {
    background: linear-gradient(90deg, rgb(251 113 133 / 0.14), transparent 60%);
  }
  .row.flash::before {
    background: var(--g-alert);
    box-shadow: 0 0 10px var(--g-alert);
  }
  .text .chip {
    margin-right: 6px;
    vertical-align: 1px;
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
  .text {
    color: var(--g-text);
    overflow-wrap: anywhere;
  }
  .from {
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    color: var(--g-accent-a);
    font-weight: 600;
    cursor: pointer;
  }
  .from:hover {
    text-decoration: underline;
  }
  @keyframes acquire {
    from {
      background-color: rgb(103 232 249 / 0.16);
    }
  }
  @media (max-width: 720px) {
    .row {
      grid-template-columns: 4.6rem 2.4rem 1fr;
      padding-inline: var(--g-space-3);
    }
    .kind,
    .off {
      display: none;
    }
  }
</style>
