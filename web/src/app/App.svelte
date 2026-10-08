<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { GhostApp } from '../lib/state/app.svelte';
  import { provideApp } from '../lib/state/context';
  import Logo from '../components/Logo.svelte';
  import ClassificationBanner from '../features/status/ClassificationBanner.svelte';
  import SituationBar from '../features/status/SituationBar.svelte';
  import StatusPanel from '../features/status/StatusPanel.svelte';
  import ReceiverPanel from '../features/receiver/ReceiverPanel.svelte';
  import TuningPanel from '../features/tuning/TuningPanel.svelte';
  import AudioPanel from '../features/audio/AudioPanel.svelte';
  import WaterfallPanel from '../features/waterfall/WaterfallPanel.svelte';
  import TimelinePanel from '../features/timeline/TimelinePanel.svelte';
  import StationsPanel from '../features/stations/StationsPanel.svelte';
  import MapPanel from '../features/map/MapPanel.svelte';
  import { formatMHz } from '../lib/format';

  let { url }: { url?: string } = $props();
  // svelte-ignore state_referenced_locally
  const app = new GhostApp(url);
  provideApp(app);

  type Tab = 'traffic' | 'waterfall' | 'stations' | 'map' | 'controls' | 'status';
  const TABS: readonly [Tab, string][] = [
    ['traffic', 'Traffic'],
    ['waterfall', 'Waterfall'],
    ['stations', 'Stations'],
    ['map', 'Map'],
    ['controls', 'Controls'],
    ['status', 'Status'],
  ];
  let tab = $state<Tab>('traffic');
  let phone = $state(false);
  let receiverPanel: { focusSearch(): void } | undefined = $state();

  const show = (t: Tab): boolean => !phone || tab === t;
  const session = $derived(app.state.session);

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
    window.addEventListener('pagehide', release);
    app.start();
    return () => {
      mq.removeEventListener('change', update);
      window.removeEventListener('pagehide', release);
    };
  });
  onDestroy(release);
</script>

<ClassificationBanner />

<div class="shell">
  <header class="masthead">
    <Logo size={34} />
    <div class="ident">
      <span class="sub caps">JS8 listening post · KiwiSDR</span>
      {#if session?.receiver}
        <span class="mono rx">
          {session.receiver.name ?? session.receiver.host} · {formatMHz(session.tuning.dial_hz)} MHz
        </span>
      {/if}
    </div>
  </header>

  <SituationBar onSwitch={switchReceiver} />

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
      {#if show('status')}<StatusPanel />{/if}
      {#if show('stations')}<StationsPanel />{/if}
      {#if show('map')}<MapPanel />{/if}
    </div>
  </main>

  <footer class="foot mono">
    ghost.js8 · receive-only · decodes by native JS8Call · build {app.state.hello?.build ?? '—'}
  </footer>
</div>

<style>
  .shell {
    max-width: 1680px;
    margin: 0 auto;
    padding: var(--g-space-3) var(--g-gutter) var(--g-space-5);
    display: grid;
    gap: var(--g-space-3);
  }
  .masthead {
    display: flex;
    align-items: center;
    gap: var(--g-space-4);
  }
  .ident {
    display: grid;
    gap: 2px;
    min-width: 0;
  }
  .sub {
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  .rx {
    font-size: var(--g-text-s);
    color: var(--g-signal);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .grid {
    display: grid;
    gap: var(--g-space-3);
    grid-template-columns: minmax(280px, 340px) minmax(0, 1fr) minmax(300px, 380px);
    align-items: start;
  }
  .col {
    display: grid;
    gap: var(--g-space-3);
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
    gap: var(--g-space-1);
    overflow-x: auto;
    padding-bottom: 2px;
  }
  .tab {
    flex: none;
    padding: var(--g-space-2) var(--g-space-3);
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-s);
    background: var(--g-glass);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    cursor: pointer;
  }
  .tab[aria-current='page'] {
    border-color: var(--g-signal);
    color: var(--g-signal);
  }
  .foot {
    font-size: var(--g-text-xs);
    color: var(--g-text-dim);
    text-align: center;
  }
</style>
