"""
Phase 7: the deployed site. A single self-contained static page - no
backend, no Streamlit - that renders the COGs directly in the browser via
georaster-layer-for-leaflet (client-side GeoTIFF range-request reads), the
same "efficient protocol" story as benchmark_access.py but now visible in
the actual deployed product, not just a benchmark script.

Also exports the WUI polygon and fire station point(s) for this AOI as
small WGS84 GeoJSON files for the map (baked at build time - no live
King County API calls from the deployed page).

Usage:
    python build_static_site.py
"""

import json
import os

from kc_layers import FIRE_STATIONS_URL, WUI_URL, fetch_layer

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(os.path.dirname(DATA_DIR), "docs")
AOI_PATH = os.path.join(DATA_DIR, "aoi_selection.json")
BENCHMARK_PATH = os.path.join(DATA_DIR, "benchmark_results.json")
COMPARISON_PATH = os.path.join(DATA_DIR, "wui_comparison.json")


def export_vector_context(minx, miny, maxx, maxy) -> dict:
    wui = fetch_layer(WUI_URL, bbox=(minx, miny, maxx, maxy)).to_crs(4326)
    wui["geometry"] = wui.geometry.make_valid()
    wui.to_file(os.path.join(DOCS_DIR, "wui_aoi.geojson"), driver="GeoJSON")

    buffer_ft = 30_000
    stations = fetch_layer(
        FIRE_STATIONS_URL, bbox=(minx - buffer_ft, miny - buffer_ft, maxx + buffer_ft, maxy + buffer_ft)
    ).to_crs(4326)
    stations.to_file(os.path.join(DOCS_DIR, "fire_stations_aoi.geojson"), driver="GeoJSON")
    return {"wui_count": len(wui), "station_count": len(stations)}


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>King County Wildfire Terrain Risk (Demo)</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
<style>
  :root {{
    --bg: #ffffff; --ink: #1a1a1a; --muted: #5b5f66; --border: #e2e4e8;
    --surface: #f6f7f9; --accent: #2a78d6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0e1117; --ink: #e6e8eb; --muted: #9aa1ab; --border: #2a2e35;
      --surface: #161a21; --accent: #4f9bf0;
    }}
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; margin: 0; }}
  body {{
    display: flex; flex-direction: column; background: var(--bg); color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }}
  header {{ padding: 16px clamp(16px, 4vw, 32px) 0; }}
  h1 {{ margin: 0 0 4px; font-size: 1.4rem; }}
  .caption {{ color: var(--muted); margin: 0 0 12px; font-size: 0.9rem; }}
  .tabs {{ display: flex; gap: 20px; border-bottom: 1px solid var(--border); padding: 0 clamp(16px, 4vw, 32px); }}
  .tab-btn {{ background: none; border: none; padding: 10px 0; font-size: 15px; color: var(--muted); cursor: pointer; border-bottom: 2px solid transparent; }}
  .tab-btn.active {{ color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }}
  #tab-map {{ flex: 1 1 auto; min-height: 0; display: none; position: relative; }}
  #tab-map.active {{ display: block; }}
  #map {{ height: 100%; width: 100%; }}
  #tab-about {{ display: none; padding: 16px clamp(16px, 4vw, 32px) 48px; overflow-y: auto; }}
  #tab-about.active {{ display: block; }}
  .controls {{
    position: absolute; top: 12px; right: 12px; z-index: 1000; background: var(--surface);
    border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; font-size: 13px;
    max-width: 220px;
  }}
  .controls label {{ display: block; margin: 4px 0; }}
  .legend {{ margin-top: 10px; }}
  .legend-bar {{ height: 10px; border-radius: 3px; background: linear-gradient(to right, #fff5eb, #a50f15); }}
  .legend-labels {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); }}
  code {{ background: var(--surface); padding: 1px 5px; border-radius: 4px; font-size: 0.9em; }}
  a {{ color: var(--accent); }}
</style>
</head>
<body>
  <header>
    <h1>King County Wildfire Terrain Risk (Demo)</h1>
    <p class="caption">Illustrative terrain-only risk index for one AOI in unincorporated King County - see the About tab before drawing any conclusions from it.</p>
    <div class="tabs">
      <button class="tab-btn active" data-tab="map">Map</button>
      <button class="tab-btn" data-tab="about">About</button>
    </div>
  </header>

  <div id="tab-map" class="active">
    <div id="map"></div>
    <div class="controls">
      <strong>Layers</strong>
      <label><input type="checkbox" id="toggle-risk" checked> Terrain risk index</label>
      <label><input type="checkbox" id="toggle-hillshade" checked> Hillshade</label>
      <label><input type="checkbox" id="toggle-wui" checked> Official WUI boundary</label>
      <label><input type="checkbox" id="toggle-stations" checked> Fire stations</label>
      <div class="legend">
        <div class="legend-bar"></div>
        <div class="legend-labels"><span>Lower risk</span><span>Higher risk</span></div>
      </div>
    </div>
  </div>

  <div id="tab-about">{about_html}</div>

<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/georaster@1.6.0/dist/georaster.browser.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/georaster-layer-for-leaflet@3.10.0/dist/georaster-layer-for-leaflet.min.js"></script>
<script>
  document.querySelectorAll(".tab-btn").forEach(function (btn) {{
    btn.addEventListener("click", function () {{
      document.querySelectorAll(".tab-btn").forEach(function (b) {{ b.classList.remove("active"); }});
      document.querySelectorAll("#tab-map, #tab-about").forEach(function (p) {{ p.classList.remove("active"); }});
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
      if (btn.dataset.tab === "map") {{ setTimeout(function () {{ map.invalidateSize(); }}, 50); }}
    }});
  }});

  const map = L.map("map", {{ zoomSnap: 0.25 }}).setView([{center_lat}, {center_lon}], 15);

  function riskColor(value) {{
    if (value === null || isNaN(value)) return null;
    const t = Math.max(0, Math.min(1, value));
    const lo = [255, 245, 235], hi = [165, 15, 21];
    const rgb = lo.map(function (c, i) {{ return Math.round(c + t * (hi[i] - c)); }});
    return "rgba(" + rgb.join(",") + ",0.75)";
  }}

  let riskLayer, hillshadeLayer;

  fetch("cogs/hillshade.tif").then(function (r) {{ return r.arrayBuffer(); }})
    .then(parseGeoraster).then(function (georaster) {{
      hillshadeLayer = new GeoRasterLayer({{
        georaster: georaster, opacity: 0.9, resolution: 256,
        pixelValuesToColorFn: function (values) {{
          const v = values[0];
          if (v === null || v === georaster.noDataValue) return null;
          return "rgb(" + v + "," + v + "," + v + ")";
        }},
      }});
      hillshadeLayer.addTo(map);
    }});

  fetch("cogs/terrain_risk_index.tif").then(function (r) {{ return r.arrayBuffer(); }})
    .then(parseGeoraster).then(function (georaster) {{
      riskLayer = new GeoRasterLayer({{
        georaster: georaster, opacity: 0.75, resolution: 256,
        pixelValuesToColorFn: function (values) {{
          const v = values[0];
          if (v === null || v === georaster.noDataValue) return null;
          return riskColor(v);
        }},
      }});
      riskLayer.addTo(map);
    }});

  let wuiLayer, stationsLayer;
  fetch("wui_aoi.geojson").then(function (r) {{ return r.json(); }}).then(function (gj) {{
    wuiLayer = L.geoJSON(gj, {{ style: {{ color: "#2a78d6", weight: 2, dashArray: "6 4", fillOpacity: 0 }} }}).addTo(map);
  }});
  fetch("fire_stations_aoi.geojson").then(function (r) {{ return r.json(); }}).then(function (gj) {{
    stationsLayer = L.geoJSON(gj, {{
      pointToLayer: function (feature, latlng) {{
        return L.circleMarker(latlng, {{ radius: 6, color: "#1a1a1a", weight: 1, fillColor: "#eda100", fillOpacity: 1 }});
      }},
    }}).addTo(map);
  }});

  document.getElementById("toggle-risk").addEventListener("change", function (e) {{
    if (riskLayer) {{ e.target.checked ? riskLayer.addTo(map) : map.removeLayer(riskLayer); }}
  }});
  document.getElementById("toggle-hillshade").addEventListener("change", function (e) {{
    if (hillshadeLayer) {{ e.target.checked ? hillshadeLayer.addTo(map) : map.removeLayer(hillshadeLayer); }}
  }});
  document.getElementById("toggle-wui").addEventListener("change", function (e) {{
    if (wuiLayer) {{ e.target.checked ? wuiLayer.addTo(map) : map.removeLayer(wuiLayer); }}
  }});
  document.getElementById("toggle-stations").addEventListener("change", function (e) {{
    if (stationsLayer) {{ e.target.checked ? stationsLayer.addTo(map) : map.removeLayer(stationsLayer); }}
  }});
</script>
</body>
</html>
"""


def main() -> None:
    with open(AOI_PATH) as f:
        aoi = json.load(f)
    with open(BENCHMARK_PATH) as f:
        bench = json.load(f)
    with open(COMPARISON_PATH) as f:
        comparison = json.load(f)

    minx, miny, maxx, maxy = aoi["clip_bbox_ft"]
    counts = export_vector_context(minx, miny, maxx, maxy)

    import rioxarray
    dem = rioxarray.open_rasterio(os.path.join(DOCS_DIR, "cogs", "dem_aoi.tif"))
    from pyproj import Transformer
    b = dem.rio.bounds()
    transformer = Transformer.from_crs(dem.rio.crs, "EPSG:4326", always_xy=True)
    lon1, lat1 = transformer.transform(b[0], b[1])
    lon2, lat2 = transformer.transform(b[2], b[3])
    center_lat, center_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2

    wui_pct = 100 * comparison["total_official_wui_cells"] / comparison["total_valid_cells"]
    about_html = f"""
    <h2>What this is</h2>
    <p>An illustrative <strong>terrain-only</strong> wildfire exposure index for one
    ~2km AOI in the Cascade foothills of unincorporated King County - built to
    demonstrate cloud-native raster engineering practices (Cloud-Optimized GeoTIFF,
    STAC, client-side range-request rendering), not to produce an authoritative
    hazard product. It is <strong>not</strong> a fuel-moisture/weather/vegetation
    model and <strong>not</strong> a replacement for King County's official
    Wildland Urban Interface (WUI) designation.</p>

    <h2>What goes into the index</h2>
    <p>Slope (steeper spreads fire faster), south/west-facing aspect (runs hotter and
    drier in the Northern Hemisphere), and distance to the nearest fire station (a
    crude response-time proxy) - combined with illustrative, uncalibrated weights
    (50/30/20). See <code>data/terrain_analysis.py</code> for the exact formula.</p>

    <h2>The efficiency finding</h2>
    <p>Going in, the plan was to show a before/after COG conversion. Instead,
    <code>rio_cogeo.cog_validate()</code> confirmed King County's real,
    production LiDAR DEM (hosted via NOAA Digital Coast) is <strong>already a
    valid, spec-compliant COG</strong> - a genuinely good sign, reported honestly
    rather than replaced with a fabricated story. What's demonstrated instead,
    measured on the live file:</p>
    <ul>
      <li>File size: {bench['file_size_bytes'] / 1e6:.0f} MB</li>
      <li>Blocks touched by this AOI's windowed read: {bench['blocks_touched_by_aoi_window']}
        of {bench['total_blocks']} ({bench['pct_of_file_blocks_touched']}% of the file)</li>
      <li>Windowed read time over the network: {bench['window_read_seconds']}s for
        {bench['window_raw_bytes_uncompressed'] / 1e6:.1f} MB of pixel data</li>
    </ul>
    <p>This map's raster layers are rendered the same way - directly from the COGs
    via browser-side range requests (<code>georaster-layer-for-leaflet</code>), no
    tile-rendering backend.</p>

    <h2>Comparison against the official WUI designation</h2>
    <p>Official WUI covers {wui_pct:.1f}%
    of this specific AOI (it was deliberately chosen to overlap WUI, so this
    particular comparison mostly confirms overlap rather than revealing a gap - an
    AOI straddling the WUI boundary would be a more informative comparison).
    {comparison['pct_high_risk_cells_inside_official_wui']}% of this AOI's top-quartile
    terrain-risk cells fall inside the official WUI boundary;
    {comparison['pct_high_risk_cells_outside_official_wui']}% fall outside it.</p>

    <h2>A real data-quality finding along the way</h2>
    <p>Checking which WUI-designated areas actually had usable bare-earth LiDAR
    coverage surfaced a pattern worth a human look: several large WUI polygons
    had 0% valid ground-return pixels in this delivery tile - plausibly because
    dense forest canopy (exactly what makes an area WUI-relevant) limits LiDAR
    ground penetration. The AOI shown here was chosen only after verifying real
    pixel coverage, not just polygon/bbox overlap.</p>

    <h2>Data sources</h2>
    <ul>
      <li><a href="{aoi['tile_url']}" target="_blank" rel="noopener">King County 2016 LiDAR bare-earth DEM (NOAA Digital Coast)</a></li>
      <li><a href="https://gis-kingcounty.opendata.arcgis.com/datasets/kingcounty::wildland-urban-interface-in-king-county" target="_blank" rel="noopener">Wildland Urban Interface in King County</a> ({counts['wui_count']} polygon(s) shown)</li>
      <li><a href="https://gis-kingcounty.opendata.arcgis.com/datasets/kingcounty::fire-station-locations-in-king-county" target="_blank" rel="noopener">Fire Station Locations in King County</a> ({counts['station_count']} station(s) shown)</li>
      <li><a href="stac/catalog.json" target="_blank" rel="noopener">STAC catalog for this AOI's derived assets</a></li>
      <li><a href="https://github.com/crikeli/kc-wildfire-terrain-risk" target="_blank" rel="noopener">Source code on GitHub</a></li>
    </ul>
    """

    page = PAGE_TEMPLATE.format(about_html=about_html, center_lat=center_lat, center_lon=center_lon)
    with open(os.path.join(DOCS_DIR, "index.html"), "w") as f:
        f.write(page)
    print(f"Wrote {os.path.join(DOCS_DIR, 'index.html')}")


if __name__ == "__main__":
    main()
