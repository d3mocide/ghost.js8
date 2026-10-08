<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import { useApp } from '../../lib/state/context';
  import { stationList } from '../../lib/state/state';
  import { ago, formatSnr } from '../../lib/format';

  const app = useApp();
  const stations = $derived(stationList(app.state));
</script>

<Panel id="stations" code="HRD" title="Heard stations" flush>
  {#snippet actions()}
    <span class="count mono">{stations.length}</span>
  {/snippet}
  {#if stations.length === 0}
    <p class="empty">No stations heard yet.</p>
  {:else}
    <div class="scroll">
      <table>
        <thead>
          <tr
            ><th scope="col">Callsign</th><th scope="col">Heard</th><th scope="col">SNR</th><th
              scope="col">Grid</th
            ><th scope="col">Count</th></tr
          >
        </thead>
        <tbody>
          {#each stations as s (s.callsign)}
            <tr data-testid="station-row">
              <th scope="row" class="mono call">{s.callsign}</th>
              <td class="mono">{ago(s.last_heard_utc, app.now)}</td>
              <td class="mono num">{formatSnr(s.snr_db)}</td>
              <td class="mono">{s.grid ?? '—'}</td>
              <td class="mono num">{s.heard_count}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</Panel>

<style>
  .count {
    color: var(--g-chrome);
    font-size: var(--g-text-s);
  }
  .empty {
    margin: 0;
    padding: var(--g-space-4);
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
  }
  .scroll {
    max-height: 18rem;
    overflow: auto;
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
    position: sticky;
    top: 0;
    background: var(--g-glass-strong);
    color: var(--g-text-muted);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    font-weight: 400;
    letter-spacing: var(--g-tracking-caps);
    text-transform: uppercase;
  }
  .call {
    color: var(--g-signal);
    font-weight: 600;
  }
</style>
