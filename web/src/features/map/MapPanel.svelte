<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import { useApp } from '../../lib/state/context';
  import { mappableStations } from '../../lib/state/state';
  import { gridCenter } from '../../lib/grid';
  import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
  import type { Feature, FeatureCollection } from 'geojson';
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';

  const app = useApp();
  let el: HTMLDivElement | undefined = $state();
  let map: MapLibreMap | null = $state(null);
  let failed = $state<string | null>(null);
  const stations = $derived(mappableStations(app.state));

  function stationGeoJson(): FeatureCollection {
    return {
      type: 'FeatureCollection',
      features: stations.flatMap((s) => {
        const c = gridCenter(s.grid);
        return c
          ? [
              {
                type: 'Feature',
                properties: { callsign: s.callsign, grid: s.grid, snr: s.snr_db },
                geometry: { type: 'Point', coordinates: c },
              },
            ]
          : [];
      }),
    };
  }

  function fieldLines(): FeatureCollection {
    // Maidenhead field boundaries: every 20 deg longitude, 10 deg latitude.
    const features: Feature[] = [];
    for (let lon = -180; lon <= 180; lon += 20) {
      features.push({
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'LineString',
          coordinates: [
            [lon, -85],
            [lon, 85],
          ],
        },
      });
    }
    for (let lat = -80; lat <= 80; lat += 10) {
      features.push({
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'LineString',
          coordinates: [
            [-180, lat],
            [180, lat],
          ],
        },
      });
    }
    return { type: 'FeatureCollection', features };
  }

  $effect(() => {
    if (!el) return;
    const container = el;
    const life = { disposed: false };
    let instance: MapLibreMap | null = null;
    void (async () => {
      try {
        const maplibre = await import('maplibre-gl');
        maplibre.setWorkerUrl(workerUrl); // self-contained worker, emitted as a hashed asset
        await import('maplibre-gl/dist/maplibre-gl.css');
        if (life.disposed) return;
        instance = new maplibre.Map({
          container,
          attributionControl: { compact: true, customAttribution: 'Natural Earth' },
          center: [-40, 30],
          zoom: 0.6,
          renderWorldCopies: false,
          style: {
            version: 8,
            sources: {
              land: { type: 'geojson', data: '/map/land.geojson' },
              borders: { type: 'geojson', data: '/map/borders.geojson' },
              fields: { type: 'geojson', data: fieldLines() },
              stations: { type: 'geojson', data: stationGeoJson() },
            },
            layers: [
              { id: 'bg', type: 'background', paint: { 'background-color': '#060814' } },
              {
                id: 'fields',
                type: 'line',
                source: 'fields',
                paint: { 'line-color': 'rgba(125,211,252,0.06)', 'line-width': 1 },
              },
              {
                id: 'land',
                type: 'fill',
                source: 'land',
                paint: { 'fill-color': '#151a38', 'fill-outline-color': 'rgba(167,139,250,0.4)' },
              },
              {
                id: 'borders',
                type: 'line',
                source: 'borders',
                paint: { 'line-color': 'rgba(167,139,250,0.22)', 'line-width': 0.6 },
              },
              {
                id: 'halo',
                type: 'circle',
                source: 'stations',
                paint: {
                  'circle-radius': 10,
                  'circle-color': 'rgba(94,234,212,0.18)',
                  'circle-blur': 0.6,
                },
              },
              {
                id: 'dots',
                type: 'circle',
                source: 'stations',
                paint: {
                  'circle-radius': 3.5,
                  'circle-color': '#5eead4',
                  'circle-stroke-color': '#060814',
                  'circle-stroke-width': 1,
                },
              },
            ],
          },
        });
        const m = instance;
        m.on('click', 'dots', (e) => {
          const f = e.features?.[0];
          const props = f?.properties as
            { callsign?: string; grid?: string; snr?: number } | undefined;
          if (!f || !props?.callsign || f.geometry.type !== 'Point') return;
          new maplibre.Popup({ closeButton: false })
            .setLngLat(f.geometry.coordinates as [number, number])
            .setText(
              `${props.callsign} · ${props.grid ?? ''}${props.snr !== undefined ? ` · ${String(props.snr)} dB` : ''}`,
            )
            .addTo(m);
        });
        m.on('load', () => {
          map = m;
        });
      } catch (err) {
        failed = err instanceof Error ? err.message : String(err);
      }
    })();
    return () => {
      life.disposed = true;
      instance?.remove();
      map = null;
    };
  });

  $effect(() => {
    const data = stationGeoJson();
    void map?.getSource<GeoJSONSource>('stations')?.setData(data);
  });
</script>

<Panel id="map" code="MAP" title="Station map" flush>
  {#snippet actions()}
    <span class="count mono">{stations.length} with grid</span>
  {/snippet}
  <div
    class="map"
    bind:this={el}
    role="region"
    aria-label={`Map of ${String(stations.length)} heard stations with valid Maidenhead grids. The heard stations table lists the same stations.`}
  ></div>
  {#if failed}<p class="error">Map unavailable: {failed}</p>{/if}
  <p class="note">Only stations that sent a valid Maidenhead grid are plotted.</p>
</Panel>

<style>
  .map {
    height: clamp(200px, 26vh, 280px);
    background: #060814;
  }
  .count {
    color: var(--g-chrome);
    font-size: var(--g-text-xs);
  }
  .note,
  .error {
    margin: 0;
    padding: var(--g-space-2) var(--g-space-3);
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  .error {
    color: var(--g-warn);
  }
  :global(.maplibregl-popup-content) {
    background: var(--g-glass-strong);
    color: var(--g-text);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    border: 1px solid var(--g-border-strong);
  }
  :global(.maplibregl-popup-tip) {
    display: none;
  }
  :global(.maplibregl-ctrl-attrib) {
    background: rgb(5 6 10 / 0.7) !important;
    color: var(--g-text-muted);
  }
</style>
