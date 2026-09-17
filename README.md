# King County Wildfire Terrain Risk (Demo)

An illustrative, terrain-only wildfire exposure index for a small AOI in
the Cascade foothills of unincorporated King County, WA - built as a
portfolio piece demonstrating cloud-native raster engineering practices
(Cloud-Optimized GeoTIFF, STAC, client-side range-request rendering), not
to produce an authoritative hazard product.

**Live site: https://crikeli.github.io/kc-wildfire-terrain-risk/**

## Status: complete, live on GitHub Pages

Third in a King County GIS portfolio series, after `seattle-house-styles`
and `kc-data-quality-audit`. Unlike the house-styles project, there's no
permission blocker here - the LiDAR elevation data (NOAA/USGS/PSLC) is
public domain, and the vector layers are the same open King County GIS
data already used in `kc-data-quality-audit`.

## What this is - and isn't

This is **not** a fuel-moisture/weather/vegetation-type wildfire risk model
and **not** a replacement for King County's official [Wildland Urban
Interface](https://gis-kingcounty.opendata.arcgis.com/datasets/kingcounty::wildland-urban-interface-in-king-county)
(WUI) designation. It combines three terrain factors - slope, south/west
aspect, and distance to the nearest fire station - with illustrative,
uncalibrated weights, to demonstrate a real raster analysis pipeline end
to end. See the site's About tab for the full methodology and every
caveat.

## How it works

**Finding the data.** King County's own "imagery" service turned out to be
a pre-cached RGB basemap (no raw pixel access) - the real analytical raster
is King County's 2016 LiDAR bare-earth DEM, public and unauthenticated via
[NOAA Digital Coast](https://coast.noaa.gov/htdata/raster2/elevation/WA_King_DEM_2016_8589/).
The vector context (Wildland Urban Interface, fire stations, the
unincorporated-King-County boundary) comes from the same King County GIS
REST services used in `kc-data-quality-audit` (`data/kc_layers.py`).

**Picking the AOI (`data/select_aoi.py`).** Not a guess: reads just the
header of each of the DEM's 5 delivery tiles via GDAL's `/vsicurl/` (no
download), finds where the official WUI layer actually overlaps
unincorporated King County, and - critically - verifies real pixel
coverage with a windowed test read before committing to a spot. The first
candidate (the tile with the *largest* WUI overlap) turned out to have
almost no usable LiDAR data at the largest WUI polygons - a real finding,
not a bug: dense forest canopy (exactly what makes an area WUI-relevant)
limits how many laser pulses reach the ground.

**The efficiency finding (`data/benchmark_access.py`).** The original plan
was a before/after COG conversion demo. Instead, `rio_cogeo.cog_validate()`
confirmed King County's real, production DEM (as hosted by NOAA) is
**already a valid, spec-compliant COG** - reported honestly rather than
replaced with a fabricated story. What's demonstrated instead, measured on
the live 1.35 GB file: a small AOI windowed read touches only 25 of 22,776
internal blocks (0.11% of the file) and completes in about a second.

**Building the AOI COG (`data/build_cog.py`).** Clips the AOI via a
windowed read (no full download), converts to a validated COG with a
floating-point predictor for real compression gains (the DEM export
shrank from 16.6 MB to 11.6 MB just from that one setting).

**Terrain analysis (`data/terrain_analysis.py`).** Slope, aspect, and
hillshade via `xarray-spatial` (the right tool for raster-native surface
analysis - no deep learning was used here on purpose, since this isn't a
classification/detection problem; see the module docstring). Distance to
the nearest fire station is computed as plain vectorized Euclidean
distance, not `xarray-spatial`'s grid-internal `proximity()`, since the
nearest station sits outside this small AOI entirely.

**Comparison against the real WUI layer (`data/compare_to_wui.py`).**
Checks how much of the terrain-only high-risk area falls inside the
official WUI boundary - reported honestly, including the limitation that
this particular AOI was chosen for already overlapping WUI, so the
comparison mostly confirms overlap rather than revealing a gap.

**STAC catalog (`data/build_stac_catalog.py`).** A minimal, real STAC
Catalog -> Collection -> Item describing every derived COG with correct
extent and media type - the actual current standard for cataloging
cloud-native geospatial assets.

**The deployed site (`data/build_static_site.py`).** GitHub Pages serves
static files only, so the map renders the COGs directly in the browser via
[georaster-layer-for-leaflet](https://github.com/GeoTIFF/georaster-layer-for-leaflet)
- real client-side range-request reads, no tile-rendering backend. (One
real bug hit and fixed along the way: calling `map.fitBounds()` right
after adding the raster layer raced with its in-progress tile rendering
and left some map tiles permanently blank - removing that call and setting
the initial view directly fixed it.)

## Known limitations

- Single small (~2km) AOI, not countywide - the pipeline works at this
  scale; scaling it up would need a tiled-processing strategy, not just a
  bigger clip.
- Terrain-only index - no fuel moisture, weather, vegetation type/density,
  or historical fire data.
- Composite weights (50% slope / 30% aspect / 20% distance-to-station) are
  illustrative, not calibrated against any real fire-behavior model.
- The WUI comparison isn't very discriminating for this specific AOI,
  since it was chosen for already overlapping WUI - an AOI straddling the
  boundary would be more informative.

## Repo layout

```
data/
  kc_layers.py            # shared config + fetch helper for the King County vector layers used
  select_aoi.py            # data-driven AOI selection (real pixel-coverage check, not just bbox overlap)
  benchmark_access.py       # the COG efficiency measurement
  build_cog.py              # clips + converts the AOI DEM to a validated COG
  terrain_analysis.py       # slope/aspect/hillshade/distance/composite risk, via xarray-spatial
  compare_to_wui.py         # terrain risk vs. the official WUI layer
  build_stac_catalog.py     # STAC catalog for the derived COGs
  build_static_site.py      # renders docs/index.html + exports AOI GeoJSON context
docs/
  index.html                # the deployed static site
  cogs/*.tif                # the published COGs (DEM + 5 derived layers)
  stac/                     # the STAC catalog
  wui_aoi.geojson, fire_stations_aoi.geojson
environment.yml
```

## Setup

```bash
conda env create -f environment.yml
conda activate kc-wildfire-terrain-risk
```

```bash
python data/select_aoi.py
python data/benchmark_access.py
python data/build_cog.py
python data/terrain_analysis.py
python data/compare_to_wui.py
python data/build_stac_catalog.py
python data/build_static_site.py
```

## Stack

rasterio, rioxarray, xarray-spatial, rio-cogeo, pystac, geopandas - Leaflet
+ georaster-layer-for-leaflet for the deployed static site.
