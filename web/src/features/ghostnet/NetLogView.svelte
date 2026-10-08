<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import Pill from '../../components/Pill.svelte';
  import { classify } from '../../lib/ghostnet';
  import { formatMHz, formatSnr, utcDateTime, utcTime } from '../../lib/format';
  import type { NetLog } from '../../lib/protocol/generated';

  let { netId }: { netId: string } = $props();

  let log = $state<NetLog | null>(null);
  let error = $state<string | null>(null);
  let audio: HTMLAudioElement | undefined = $state();

  $effect(() => {
    const id = netId;
    log = null;
    error = null;
    void (async () => {
      try {
        const res = await fetch(`/api/nets/${id}`);
        if (!res.ok)
          throw new Error(res.status === 404 ? 'no such recording' : `HTTP ${String(res.status)}`);
        log = (await res.json()) as NetLog;
      } catch (err) {
        error = err instanceof Error ? err.message : String(err);
      }
    })();
  });

  const s = $derived(log?.summary);
  const started = $derived(s ? Date.parse(s.started) : 0);
  const seconds = $derived(log?.waterfall_seconds ?? 0);
  const minuteTicks = $derived(
    Array.from({ length: Math.floor(seconds / 300) + 1 }, (_, i) => i * 300).filter(
      (t) => t <= seconds,
    ),
  );
  const offsetTicks = [0, 500, 1000, 1500, 2000, 2500, 3000];
  const offsetPct = (hz: number): number =>
    log
      ? ((hz - log.waterfall_offset_lo_hz) /
          (log.waterfall_offset_hi_hz - log.waterfall_offset_lo_hz)) *
        100
      : 0;
  const rows = $derived(
    (log?.decodes ?? []).map((d) => ({
      ...d,
      tags: classify(d.text),
      at: (Date.parse(d.utc) - started) / 1000,
    })),
  );

  function seek(t: number): void {
    if (!audio || !s?.has_audio) return;
    audio.currentTime = Math.max(0, t);
    void audio.play();
  }

  function seekFromWaterfall(ev: MouseEvent): void {
    const el = ev.currentTarget as HTMLElement;
    const r = el.getBoundingClientRect();
    seek(((ev.clientY - r.top) / r.height) * seconds);
  }
</script>

<div class="view" data-testid="net-log">
  <nav><a href="#/" class="back mono">← LIVE</a></nav>

  {#if error}
    <p class="error" role="alert">Recording unavailable: {error}</p>
  {:else if !log || !s}
    <p class="muted">Loading recording…</p>
  {:else}
    <header class="head">
      <h1>{s.label}</h1>
      <div class="meta mono">
        {utcDateTime(s.scheduled_start)} – {utcTime(s.scheduled_end)}Z · {s.band} · {formatMHz(
          s.dial_hz,
        )} MHz
      </div>
      <div class="meta">
        {s.receiver ?? 'no receiver recorded'}{s.receiver_reason ? ` — ${s.receiver_reason}` : ''}
      </div>
      <div class="pills">
        <Pill tone="info" label={`${String(s.decode_count)} decodes`} />
        <Pill tone="info" label={`${String(s.station_count)} stations`} />
        {#if s.flash_count > 0}<Pill
            tone="alert"
            label={`${String(s.flash_count)} @GSTFLASH`}
          />{/if}
        {#if s.operator_override}<Pill tone="warn" label="operator retuned during net" />{/if}
        {#if s.ended === null}<Pill tone="alert" label="recording in progress" />{/if}
      </div>
    </header>

    <div class="grid">
      <Panel id="net-waterfall" code="W/F" title="Waterfall replay" flush>
        {#if s.has_waterfall && seconds > 0}
          <div class="wf-axis mono" aria-hidden="true">
            {#each offsetTicks as t (t)}<span style:left={`${String(offsetPct(t))}%`}>{t}</span
              >{/each}
          </div>
          <div class="wf">
            <div class="tticks mono" aria-hidden="true">
              {#each minuteTicks as t (t)}
                <span style:top={`${String((t / seconds) * 100)}%`}>+{Math.round(t / 60)}m</span>
              {/each}
            </div>
            <button
              type="button"
              class="wf-img"
              onclick={seekFromWaterfall}
              disabled={!s.has_audio}
              aria-label={s.has_audio
                ? 'Waterfall: click a moment to play the audio from there'
                : 'Waterfall image'}
            >
              <img
                src={`/api/nets/${s.id}/waterfall.png`}
                alt={`Waterfall of ${s.label}: audio offsets ${String(log.waterfall_offset_lo_hz)} to ${String(log.waterfall_offset_hi_hz)} Hz, one row per second, ${String(Math.round(seconds / 60))} minutes`}
                style:height={`${String(Math.min(Math.max(seconds, 120), 900))}px`}
                data-testid="net-waterfall"
              />
            </button>
          </div>
          <p class="note">
            Newest at the bottom. Synthetic receivers produce synthetic waterfalls.
          </p>
        {:else}
          <p class="muted pad">No waterfall recorded.</p>
        {/if}
      </Panel>

      <div class="col">
        <Panel id="net-audio" code="AUD" title="Audio">
          {#if s.has_audio}
            <audio
              bind:this={audio}
              controls
              preload="metadata"
              src={`/api/nets/${s.id}/audio.flac`}
              data-testid="net-audio"
            ></audio>
            <p class="links">
              <a href={`/api/nets/${s.id}/audio.flac`} download>Download FLAC</a> ·
              <a href={`/api/nets/${s.id}/waterfall.png`} download>Download waterfall</a>
            </p>
          {:else}
            <p class="muted">No audio recorded for this net.</p>
          {/if}
        </Panel>

        <Panel id="net-stations" code="HRD" title="Stations heard" flush>
          {#if log.stations.length === 0}
            <p class="muted pad">No stations.</p>
          {:else}
            <table>
              <thead
                ><tr
                  ><th scope="col">Callsign</th><th scope="col">SNR</th><th scope="col">Grid</th><th
                    scope="col">Count</th
                  ></tr
                ></thead
              >
              <tbody>
                {#each log.stations as st (st.callsign)}
                  <tr>
                    <th scope="row" class="mono call">{st.callsign}</th>
                    <td class="mono">{formatSnr(st.snr_db)}</td>
                    <td class="mono">{st.grid ?? '—'}</td>
                    <td class="mono">{st.heard_count}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </Panel>
      </div>
    </div>

    <Panel id="net-traffic" code="TRF" title="Traffic" flush>
      {#if rows.length === 0}
        <p class="muted pad">No traffic copied during this window.</p>
      {:else}
        <ol class="traffic" data-testid="net-traffic">
          {#each rows as d, i (i)}
            <li class:flash={d.tags.flash} class:gn={d.tags.ghostnet}>
              <button
                type="button"
                class="t mono"
                onclick={() => {
                  seek(d.at);
                }}
                disabled={!s.has_audio}
                title="Play from here"
              >
                {utcTime(d.utc)}Z
              </button>
              <span class="mono num snr">{formatSnr(d.snr_db)}</span>
              <span class="mono num">{d.offset_hz}</span>
              <span class="tags">
                {#if d.tags.flash}<span class="tag alert">FLASH</span>{/if}
                {#if d.tags.ghostnet}<span class="tag gn">{d.tags.regional ?? 'GN'}</span>{/if}
                {#if d.kind === 'directed'}<span class="tag dir">DIR</span>{/if}
              </span>
              <span class="mono text">{d.text}</span>
            </li>
          {/each}
        </ol>
      {/if}
    </Panel>
  {/if}
</div>

<style>
  .view {
    display: grid;
    gap: var(--g-space-3);
  }
  .back {
    color: var(--g-chrome);
    text-decoration: none;
    font-size: var(--g-text-xs);
    letter-spacing: var(--g-tracking-caps);
  }
  .head h1 {
    margin: 0 0 var(--g-space-1);
    font-size: var(--g-text-xl);
    font-weight: 600;
  }
  .meta {
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
  }
  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: var(--g-space-2);
    margin-top: var(--g-space-2);
  }
  .grid {
    display: grid;
    gap: var(--g-space-3);
    grid-template-columns: minmax(0, 1.4fr) minmax(280px, 1fr);
    align-items: start;
  }
  @media (max-width: 960px) {
    .grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  .col {
    display: grid;
    gap: var(--g-space-3);
  }
  .wf-axis {
    position: relative;
    height: 20px;
    margin-left: 3rem;
    border-bottom: 1px solid var(--g-border);
    font-size: 10px;
    color: var(--g-text-muted);
  }
  .wf-axis span {
    position: absolute;
    top: 3px;
    transform: translateX(-50%);
  }
  .wf {
    display: grid;
    grid-template-columns: 3rem 1fr;
    max-height: 70vh;
    overflow: auto;
  }
  .tticks {
    position: relative;
    font-size: 10px;
    color: var(--g-text-muted);
  }
  .tticks span {
    position: absolute;
    right: 6px;
    transform: translateY(-50%);
  }
  .tticks span:first-child {
    transform: none; /* +0m sits at the top edge; don't clip it */
  }
  .wf-img {
    padding: 0;
    border: 0;
    background: #020308;
    cursor: crosshair;
  }
  .wf-img:disabled {
    cursor: default;
  }
  .wf-img img {
    display: block;
    width: 100%;
    image-rendering: pixelated;
  }
  .note {
    margin: 0;
    padding: var(--g-space-2) var(--g-space-3);
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  audio {
    width: 100%;
  }
  .links {
    font-size: var(--g-text-xs);
    margin: var(--g-space-2) 0 0;
  }
  .links a {
    color: var(--g-chrome);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--g-text-s);
  }
  th,
  td {
    padding: 5px var(--g-space-3);
    text-align: left;
    border-bottom: 1px solid rgb(92 225 255 / 0.06);
  }
  thead th {
    color: var(--g-text-muted);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    font-weight: 400;
    letter-spacing: var(--g-tracking-caps);
    text-transform: uppercase;
  }
  .call {
    color: var(--g-signal);
  }
  .traffic {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .traffic li {
    display: grid;
    grid-template-columns: 5.6rem 3rem 3.4rem 7rem 1fr;
    gap: var(--g-space-2);
    align-items: baseline;
    padding: 5px var(--g-space-3);
    border-bottom: 1px solid rgb(92 225 255 / 0.06);
    font-size: var(--g-text-s);
  }
  .traffic li.gn {
    background: linear-gradient(90deg, rgb(92 225 255 / 0.07), transparent 50%);
  }
  .traffic li.flash {
    background: linear-gradient(90deg, rgb(255 77 94 / 0.18), transparent 60%);
  }
  .t {
    padding: 0;
    border: 0;
    background: none;
    color: var(--g-chrome);
    text-align: left;
    cursor: pointer;
  }
  .t:disabled {
    color: var(--g-text-muted);
    cursor: default;
  }
  .snr {
    color: var(--g-chrome);
  }
  .tags {
    display: flex;
    gap: 4px;
  }
  .tag {
    font-family: var(--g-font-mono);
    font-size: 10px;
    padding: 0 4px;
    border: 1px solid currentColor;
    border-radius: 3px;
  }
  .tag.alert {
    color: var(--g-alert);
  }
  .tag.gn {
    color: var(--g-chrome);
  }
  .tag.dir {
    color: var(--g-signal);
  }
  .text {
    overflow-wrap: anywhere;
  }
  .muted {
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
  }
  .pad {
    padding: var(--g-space-3);
    margin: 0;
  }
  .error {
    color: var(--g-alert);
  }
  @media (max-width: 720px) {
    /* Tags carry meaning (FLASH, group): keep them; drop only the offset column. */
    .traffic li {
      grid-template-columns: 5rem 2.6rem 1fr;
    }
    .traffic li .num:not(.snr) {
      display: none;
    }
    .traffic li .text {
      grid-column: 1 / -1;
    }
  }
</style>
