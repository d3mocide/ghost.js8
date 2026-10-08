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
    min-width: 1.6rem;
    padding: 1px 8px;
    border-radius: var(--g-radius-pill);
    background: var(--g-accent-soft);
    color: var(--g-text);
    font-size: var(--g-text-xs);
    text-align: center;
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
    padding: 7px var(--g-space-4);
    text-align: left;
    border-bottom: 1px solid var(--g-hairline);
  }
  thead th {
    position: sticky;
    top: 0;
    background: var(--g-glass-strong);
    color: var(--g-text-muted);
    font-family: var(--g-font-mono);
    backdrop-filter: blur(12px);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .call {
    color: var(--g-accent-a);
    font-weight: 600;
  }
  tbody tr {
    transition: background var(--g-dur-fast) var(--g-ease);
  }
  tbody tr:hover {
    background: var(--g-glass-raised);
  }
</style>
