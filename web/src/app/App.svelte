<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { GhostApp } from '../lib/state/app.svelte';
  import { provideApp } from '../lib/state/context';
  import TopBar from '../features/status/TopBar.svelte';
  import Backdrop from '../components/Backdrop.svelte';
  import SituationBar from '../features/status/SituationBar.svelte';
  import StatusPanel from '../features/status/StatusPanel.svelte';
  import ReceiverPanel from '../features/receiver/ReceiverPanel.svelte';
  import TuningPanel from '../features/tuning/TuningPanel.svelte';
  import AudioPanel from '../features/audio/AudioPanel.svelte';
  import WaterfallPanel from '../features/waterfall/WaterfallPanel.svelte';
  import TimelinePanel from '../features/timeline/TimelinePanel.svelte';
  import StationsPanel from '../features/stations/StationsPanel.svelte';
  import MapPanel from '../features/map/MapPanel.svelte';
  import GhostNetPanel from '../features/ghostnet/GhostNetPanel.svelte';
  import NetLogView from '../features/ghostnet/NetLogView.svelte';
  import FlashAlert from '../features/ghostnet/FlashAlert.svelte';
  import { netIdFromHash } from '../lib/ghostnet';

  let { url }: { url?: string } = $props();
  // svelte-ignore state_referenced_locally
  const app = new GhostApp(url);
  provideApp(app);

  type Tab = 'traffic' | 'ghostnet' | 'waterfall' | 'stations' | 'map' | 'controls' | 'status';
  const TABS: readonly [Tab, string][] = [
    ['traffic', 'Traffic'],
    ['ghostnet', 'GhostNet'],
    ['waterfall', 'Waterfall'],
    ['stations', 'Stations'],
    ['map', 'Map'],
    ['controls', 'Controls'],
    ['status', 'Status'],
  ];
  let tab = $state<Tab>('traffic');
  let phone = $state(false);
  let hash = $state(typeof window === 'undefined' ? '' : window.location.hash);
  const netId = $derived(netIdFromHash(hash));
  let receiverPanel: { focusSearch(): void } | undefined = $state();

  const show = (t: Tab): boolean => !phone || tab === t;

  function switchReceiver(): void {
    tab = 'controls';
    queueMicrotask(() => {
      receiverPanel?.focusSearch();
    });
  }

  const release = (): void => {
    void app.stop();
  };

  onMount(() => {
    const mq = window.matchMedia('(max-width: 720px)');
    const update = (): void => {
      phone = mq.matches;
    };
    update();
    mq.addEventListener('change', update);
    const onHash = (): void => {
      hash = window.location.hash;
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onHash);
    window.addEventListener('pagehide', release);
    app.start();
    return () => {
      mq.removeEventListener('change', update);
      window.removeEventListener('hashchange', onHash);
      window.removeEventListener('pagehide', release);
    };
  });
  onDestroy(release);
</script>

<Backdrop />
<TopBar />

<div class="shell">
  <FlashAlert />
  <SituationBar onSwitch={switchReceiver} />

  {#if netId}
    <NetLogView {netId} />
  {:else}
    {#if phone}
      <nav class="tabs" aria-label="Views">
        {#each TABS as [id, label] (id)}
          <button
            type="button"
            class="tab"
            aria-current={tab === id ? 'page' : undefined}
            onclick={() => (tab = id)}
          >
            {label}
          </button>
        {/each}
      </nav>
    {/if}

    <main class="grid" class:phone>
      <div class="col controls">
        {#if show('controls')}
          <ReceiverPanel bind:this={receiverPanel} />
          <TuningPanel />
          <AudioPanel />
        {/if}
      </div>
      <div class="col center">
        {#if show('waterfall')}<WaterfallPanel />{/if}
        {#if show('traffic')}<TimelinePanel />{/if}
      </div>
      <div class="col side">
        {#if show('ghostnet')}<GhostNetPanel />{/if}
        {#if show('stations')}<StationsPanel />{/if}
        {#if show('map')}<MapPanel />{/if}
        {#if show('status')}<StatusPanel />{/if}
      </div>
    </main>
  {/if}

  <footer class="foot mono">
    ghost.js8 · receive-only · decodes by native JS8Call · build {app.state.hello?.build ?? '—'}
  </footer>
</div>

<style>
  .shell {
    max-width: 1680px;
    margin: 0 auto;
    padding: var(--g-space-4) var(--g-gutter) var(--g-space-6);
    display: grid;
    gap: var(--g-gap);
  }
  .grid {
    display: grid;
    gap: var(--g-gap);
    grid-template-columns: minmax(280px, 340px) minmax(0, 1fr) minmax(300px, 380px);
    align-items: start;
  }
  .col {
    display: grid;
    gap: var(--g-gap);
    min-width: 0;
  }
  .col:empty {
    display: none;
  }
  @media (max-width: 1280px) {
    .grid {
      grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
    }
    .side {
      grid-column: 1 / -1;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }
  }
  .grid.phone {
    grid-template-columns: minmax(0, 1fr);
  }
  .grid.phone .side {
    grid-template-columns: minmax(0, 1fr);
  }
  .tabs {
    display: flex;
    gap: 2px;
    overflow-x: auto;
    padding: 4px;
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-pill);
    background: var(--g-glass);
    backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
    -webkit-backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
    scrollbar-width: none;
  }
  .tab {
    flex: none;
    min-height: 34px;
    padding: 0 var(--g-space-3);
    border: 0;
    border-radius: var(--g-radius-pill);
    background: transparent;
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
    font-weight: 600;
    cursor: pointer;
    transition:
      background var(--g-dur-fast) var(--g-ease),
      color var(--g-dur-fast) var(--g-ease);
  }
  .tab[aria-current='page'] {
    background: var(--g-accent);
    color: #0a0c18;
    box-shadow: 0 6px 18px -8px rgb(125 211 252 / 0.8);
  }
  .foot {
    font-size: var(--g-text-xs);
    color: var(--g-text-dim);
    text-align: center;
    padding-top: var(--g-space-3);
  }
</style>
