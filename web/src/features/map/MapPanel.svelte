<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import { useApp } from '../../lib/state/context';
  import { mappableStations } from '../../lib/state/state';
  import { distanceKm, gridCenter, normalizeGrid } from '../../lib/grid';
  import { bearingDeg, compass, greatCircle, nightPolygon, ring } from '../../lib/geo';
  import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl';
  import type { Feature, FeatureCollection } from 'geojson';
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';

  const app = useApp();
  let el: HTMLDivElement | undefined = $state();
  let map: MapLibreMap | null = $state(null);
  let failed = $state<string | null>(null);
  const stations = $derived(mappableStations(app.state));
  const homeGrid = $derived(normalizeGrid(app.state.ghostnet?.home_grid));
  const home = $derived(gridCenter(homeGrid));
  const minute = $derived(Math.floor(app.now / 60_000)); // ages and the night shade move per minute
  const RINGS_KM = [500, 1000, 2000] as const;
  const LEGEND =
    'Your location is the yellow marker. Colour is SNR (violet weak, aqua strong) and fades with age. Dashed rings are 500, 1,000 and 2,000 km. Shaded is night. Click a station for distance and bearing.';
  const HOME_ZOOM = 2.6;
  let userMoved = false;
  let framed = false;

  const empty = (): FeatureCollection => ({ type: 'FeatureCollection', features: [] });

  function stationGeoJson(): FeatureCollection {
    return {
      type: 'FeatureCollection',
      features: stations.flatMap((s) => {
        const c = gridCenter(s.grid);
        if (!c) return [];
        const ageMin = Math.max(0, (minute * 60_000 - Date.parse(s.last_heard_utc)) / 60_000);
        return [
          {
            type: 'Feature',
            properties: {
              callsign: s.callsign,
              grid: s.grid,
              snr: s.snr_db,
              age: Math.round(ageMin),
              km: home ? Math.round(distanceKm(home, c)) : null,
              bearing: home ? Math.round(bearingDeg(home, c)) : null,
            },
            geometry: { type: 'Point', coordinates: c },
          } satisfies Feature,
        ];
      }),
    };
  }

  function homeGeoJson(): FeatureCollection {
    return home
      ? {
          type: 'FeatureCollection',
          features: [
            { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: home } },
          ],
        }
      : empty();
  }

  function ringsGeoJson(): FeatureCollection {
    if (!home) return empty();
    return {
      type: 'FeatureCollection',
      features: RINGS_KM.map((km) => ({
        type: 'Feature',
        properties: { km },
        geometry: { type: 'LineString', coordinates: ring(home, km) },
      })),
    };
  }

  function nightGeoJson(): FeatureCollection {
    return {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'Polygon', coordinates: [nightPolygon(new Date(minute * 60_000))] },
        },
      ],
    };
  }

  function linkGeoJson(to: [number, number] | null): FeatureCollection {
    if (!home || !to) return empty();
    return {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'LineString', coordinates: greatCircle(home, to) },
        },
      ],
    };
  }

  function goHome(): void {
    if (!map || !home) return;
    map.easeTo({ center: home, zoom: HOME_ZOOM, duration: 600 });
  }

  function fitAll(): void {
    if (!map) return;
    const pts: [number, number][] = stations.flatMap((s) => {
      const c = gridCenter(s.grid);
      return c ? [c] : [];
    });
    if (home) pts.push([home[0], home[1]]);
    if (pts.length === 0) return;
    const lons = pts.map((p) => p[0]);
    const lats = pts.map((p) => p[1]);
    map.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 28, maxZoom: 4.5, duration: 600 },
    );
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
              night: { type: 'geojson', data: nightGeoJson() },
              rings: { type: 'geojson', data: ringsGeoJson() },
              link: { type: 'geojson', data: empty() },
              stations: { type: 'geojson', data: stationGeoJson() },
              home: { type: 'geojson', data: homeGeoJson() },
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
                id: 'night',
                type: 'fill',
                source: 'night',
                paint: { 'fill-color': '#02030a', 'fill-opacity': 0.45 },
              },
              {
                id: 'rings',
                type: 'line',
                source: 'rings',
                paint: {
                  'line-color': 'rgba(252,211,77,0.28)',
                  'line-width': 1,
                  'line-dasharray': [2, 3],
                },
              },
              {
                id: 'link',
                type: 'line',
                source: 'link',
                paint: { 'line-color': '#7dd3fc', 'line-width': 1.6, 'line-opacity': 0.85 },
              },
              {
                id: 'halo',
                type: 'circle',
                source: 'stations',
                paint: {
                  'circle-radius': 10,
                  'circle-color': 'rgba(94,234,212,0.18)',
                  'circle-blur': 0.6,
                  'circle-opacity': ['interpolate', ['linear'], ['get', 'age'], 0, 1, 240, 0.25],
                },
              },
              {
                id: 'dots',
                type: 'circle',
                source: 'stations',
                paint: {
                  'circle-radius': 4,
                  // Weak -> strong: violet, sky, aqua.
                  'circle-color': [
                    'step',
                    ['coalesce', ['get', 'snr'], -30],
                    '#a78bfa',
                    -16,
                    '#7dd3fc',
                    -8,
                    '#5eead4',
                  ],
                  'circle-opacity': [
                    'interpolate',
                    ['linear'],
                    ['get', 'age'],
                    0,
                    1,
                    10,
                    1,
                    240,
                    0.3,
                  ],
                  'circle-stroke-color': '#060814',
                  'circle-stroke-width': 1,
                },
              },
              {
                id: 'home-ring',
                type: 'circle',
                source: 'home',
                paint: {
                  'circle-radius': 11,
                  'circle-color': 'rgba(0,0,0,0)',
                  'circle-stroke-color': 'rgba(252,211,77,0.7)',
                  'circle-stroke-width': 1.5,
                },
              },
              {
                id: 'home-dot',
                type: 'circle',
                source: 'home',
                paint: {
                  'circle-radius': 4.5,
                  'circle-color': '#fcd34d',
                  'circle-stroke-color': '#060814',
                  'circle-stroke-width': 1.5,
                },
              },
            ],
          },
        });
        const m = instance;
        const popup = new maplibre.Popup({ closeButton: false, offset: 10, maxWidth: '280px' });
        const clearLink = (): void => {
          popup.remove();
          void m.getSource<GeoJSONSource>('link')?.setData(empty());
        };
        m.on('click', (e) => {
          const f = m.queryRenderedFeatures(e.point, { layers: ['dots'] })[0];
          if (!f || f.geometry.type !== 'Point') {
            clearLink();
            return;
          }
          const props = f.properties as {
            callsign?: string;
            grid?: string;
            snr?: number | null;
            age?: number;
            km?: number | null;
            bearing?: number | null;
          };
          const at = f.geometry.coordinates as [number, number];
          const bits = [
            `${props.callsign ?? ''} · ${props.grid ?? ''}`,
            props.snr !== undefined && props.snr !== null ? `${String(props.snr)} dB` : null,
            props.km != null && props.bearing != null
              ? `${props.km.toLocaleString()} km ${compass(props.bearing)} (${String(props.bearing)}°)`
              : null,
            props.age !== undefined ? `${String(props.age)} min ago` : null,
          ].filter((x): x is string => x !== null);
          popup.setLngLat(at).setText(bits.join(' · ')).addTo(m);
          void m.getSource<GeoJSONSource>('link')?.setData(linkGeoJson(at));
        });
        m.on('mouseenter', 'dots', () => {
          m.getCanvas().style.cursor = 'pointer';
        });
        m.on('mouseleave', 'dots', () => {
          m.getCanvas().style.cursor = '';
        });
        // A viewer who pans or zooms owns the view: stop auto-framing.
        m.on('dragstart', () => {
          userMoved = true;
        });
        m.on('zoomstart', (e) => {
          if ((e as { originalEvent?: unknown }).originalEvent) userMoved = true;
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
  $effect(() => {
    const night = nightGeoJson();
    void map?.getSource<GeoJSONSource>('night')?.setData(night);
  });
  $effect(() => {
    const h = homeGeoJson();
    const r = ringsGeoJson();
    void map?.getSource<GeoJSONSource>('home')?.setData(h);
    void map?.getSource<GeoJSONSource>('rings')?.setData(r);
  });
  // Frame the view once: on home if we know it, otherwise on whatever has been heard.
  $effect(() => {
    if (!map || userMoved || framed) return;
    if (home) {
      map.jumpTo({ center: home, zoom: HOME_ZOOM });
      framed = true;
    } else if (stations.length > 0) {
      fitAll();
      framed = true;
    }
  });
</script>

<Panel id="map" code="MAP" title="Station map" flush>
  {#snippet actions()}
    {#if homeGrid}<span class="count mono" title={LEGEND}>◆ {homeGrid}</span>{/if}
    <span class="count mono">{stations.length} with grid</span>
  {/snippet}
  <div class="wrap">
    <div
      class="map"
      bind:this={el}
      role="region"
      aria-label={`Map of ${String(stations.length)} heard stations with valid Maidenhead grids. The heard stations table lists the same stations.`}
    ></div>
    <div class="tools">
      <button type="button" class="btn ghost" onclick={goHome} disabled={!home || !map}>Home</button
      >
      <button type="button" class="btn ghost" onclick={fitAll} disabled={!map}>Fit all</button>
    </div>
  </div>
  {#if failed}<p class="error">Map unavailable: {failed}</p>{/if}
</Panel>

<style>
  .wrap {
    position: relative;
  }
  .map {
    height: clamp(220px, 30vh, 340px);
    background: #060814;
  }
  .tools {
    position: absolute;
    top: var(--g-space-2);
    left: var(--g-space-2);
    display: flex;
    gap: 4px;
    z-index: 2;
  }
  .tools .btn {
    min-height: 26px;
    padding: 0 10px;
    font-size: var(--g-text-xs);
    background: rgb(5 6 10 / 0.7);
  }
  .count {
    color: var(--g-chrome);
    font-size: var(--g-text-xs);
  }
  .error {
    margin: 0;
    padding: var(--g-space-2) var(--g-space-3);
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
  }
  .error {
    color: var(--g-warn);
  }
  /* MapLibre's own stylesheet loads after ours, so these need the extra class to win. */
  :global(.maplibregl-popup .maplibregl-popup-content) {
    background: rgb(14 17 34 / 0.96);
    color: var(--g-text);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    line-height: 1.5;
    padding: 8px 12px;
    border: 1px solid var(--g-border-strong);
    border-radius: var(--g-radius-m);
    box-shadow: var(--g-shadow);
  }
  :global(.maplibregl-popup .maplibregl-popup-tip) {
    display: none;
  }
  :global(.maplibregl-ctrl-attrib) {
    background: rgb(5 6 10 / 0.7) !important;
    color: var(--g-text-muted);
  }
</style>
