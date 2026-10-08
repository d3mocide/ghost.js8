# Basemap data

| File              | Source                                                             | License       |
| ----------------- | ------------------------------------------------------------------ | ------------- |
| `land.geojson`    | Natural Earth 1:110m `ne_110m_land.geojson`                        | Public domain |
| `borders.geojson` | Natural Earth 1:110m `ne_110m_admin_0_boundary_lines_land.geojson` | Public domain |

Fetched from [`nvkelso/natural-earth-vector`](https://github.com/nvkelso/natural-earth-vector)
at commit `ca96624a56bd078437bca8184e78163e5039ad19` (2026-10-08). Upstream SHA-256:
land `9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9`,
borders `d42479fd79552cca4eec7f85fcdca717a790d29ff06be7676f1af0568c6d3f7c`.

Minified for ghost.js8: feature properties dropped, coordinates rounded to
0.01°. Served from the `web` container, so map views make no third-party
requests. A self-hosted Protomaps PMTiles basemap is the documented upgrade
path if more detail is ever needed.
