<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import Pill from '../../components/Pill.svelte';
  import type { PillTone } from '../../components/pill';
  import { useApp } from '../../lib/state/context';
  import { ago, utcTime } from '../../lib/format';
  import type { Component } from '../../lib/protocol/generated';

  const app = useApp();
  const ROWS = [
    ['bridge', 'Bridge'],
    ['decoder_process', 'Decoder process'],
    ['decoder_api', 'Decoder API'],
    ['decoder_capture', 'Decoder capturing'],
    ['receiver', 'Receiver'],
    ['audio', 'Audio feed'],
    ['waterfall', 'Waterfall feed'],
  ] as const;
  const TONE: Record<Component['state'], PillTone> = {
    ok: 'ok',
    degraded: 'warn',
    down: 'alert',
    unknown: 'unknown',
  };
  const LABEL: Record<Component['state'], string> = {
    ok: 'ONLINE',
    degraded: 'DEGRADED',
    down: 'DOWN',
    unknown: 'UNKNOWN',
  };
  const h = $derived(app.state.health);
  const overallTone = $derived<PillTone>(
    !h ? 'unknown' : h.overall === 'listening' ? 'ok' : h.overall === 'degraded' ? 'warn' : 'alert',
  );
</script>

<Panel id="status" code="SYS" title="System status">
  {#snippet actions()}
    <Pill tone={overallTone} label={h ? h.overall : 'no report'} />
  {/snippet}
  {#if !h}
    <p class="muted">Awaiting first health report from the bridge.</p>
  {:else}
    <ul class="rows">
      {#each ROWS as [key, label] (key)}
        {@const c = h.components[key]}
        <li data-testid={`health-${key}`}>
          <span class="name">{label}</span>
          <Pill tone={TONE[c.state]} label={LABEL[c.state]} title={c.detail} />
          <span class="evidence mono">
            {#if c.last_seen}seen {ago(c.last_seen, app.now)} ago{:else}—{/if}
          </span>
          {#if c.detail && c.state !== 'ok'}<span class="detail">{c.detail}</span>{/if}
        </li>
      {/each}
      <li>
        <span class="name">Last decode</span>
        <span class="mono last" data-testid="last-decode">
          {h.last_decode_utc
            ? `${utcTime(h.last_decode_utc)}Z (${ago(h.last_decode_utc, app.now)} ago)`
            : 'none yet'}
        </span>
      </li>
    </ul>
  {/if}
</Panel>

<style>
  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 4px;
  }
  li {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    align-items: center;
    gap: var(--g-space-2);
    padding: 4px 0;
    font-size: var(--g-text-s);
  }
  li + li {
    border-top: 1px solid var(--g-hairline);
    padding-top: 8px;
  }
  .last {
    grid-column: 2 / -1;
    text-align: right;
  }
  .name {
    color: var(--g-text-muted);
  }
  .evidence {
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
    min-width: 0;
    white-space: nowrap;
    text-align: right;
  }
  .detail {
    grid-column: 1 / -1;
    color: var(--g-warn);
    font-size: var(--g-text-xs);
    margin-top: -2px;
  }
  .muted {
    color: var(--g-text-muted);
    margin: 0;
  }
</style>
