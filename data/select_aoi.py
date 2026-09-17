"""
Phase 1: pick a real, data-driven AOI - not a guess. King County's 2016
LiDAR bare-earth DEM (public, no-auth, NOAA-hosted) is split into 5 large
delivery tiles covering the whole county; we only want a small clip that
actually falls inside both (a) the official Wildland Urban Interface (WUI)
layer and (b) unincorporated King County (JURIS='KC' in the cities layer -
the county's own large rural/mountainous landmass, not the small city-edge
slivers also tagged 'KC').

Each DEM tile's header (bounds, CRS, size) is read directly off the remote
file via GDAL's /vsicurl/ - this fetches only the GeoTIFF's IFD, not pixel
data, even though the files are 1-2.4 GB each. Confirmed working this
session: header reads for all 5 tiles took a few seconds combined, nowhere
near a full download.

Usage:
    python select_aoi.py
"""

import json
import os

import geopandas as gpd
import rasterio
from rasterio.windows import from_bounds
from shapely.geometry import box

from kc_layers import CITIES_URL, CRS_EPSG, WUI_URL, fetch_layer

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(DATA_DIR, "aoi_selection.json")

DEM_BASE = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/WA_King_DEM_2016_8589/"
DEM_TILES = [
    "kingcounty_delivery1_be.tif",
    "kingcounty_delivery2_be.tif",
    "kingcounty_delivery3_be.tif",
    "kingcounty_delivery4_block1_be.tif",
    "kingcounty_delivery4_block2_be.tif",
]

CLIP_HALF_WIDTH_FT = 3300  # ~1km half-width -> ~2km x 2km AOI
MIN_VALID_FRACTION = 0.9  # a candidate spot must be at least this much real data, not nodata
CANDIDATES_TO_CHECK = 15  # largest overlapping WUI polygons to try before giving up


def pick_valid_anchor(src: rasterio.DatasetReader, candidates: gpd.GeoDataFrame, tile_box) -> tuple[float, float]:
    """Tries candidate WUI polygons (largest overlap first), each via a
    real (small, cheap) windowed read, until one actually has LiDAR
    coverage - a bbox/geometry overlap alone doesn't guarantee the raster
    has real data there (data gaps, water bodies, etc. show up as nodata)."""
    ranked = candidates.sort_values("clipped_area", ascending=False).head(CANDIDATES_TO_CHECK)
    for _, row in ranked.iterrows():
        point = row.geometry.intersection(tile_box).representative_point()
        bbox = (
            point.x - CLIP_HALF_WIDTH_FT, point.y - CLIP_HALF_WIDTH_FT,
            point.x + CLIP_HALF_WIDTH_FT, point.y + CLIP_HALF_WIDTH_FT,
        )
        window = from_bounds(*bbox, transform=src.transform)
        sample = src.read(1, window=window, out_shape=(200, 200))
        valid_fraction = (sample != src.nodata).mean()
        print(f"    candidate at ({point.x:.0f}, {point.y:.0f}): {valid_fraction:.0%} valid pixels")
        if valid_fraction >= MIN_VALID_FRACTION:
            return point.x, point.y
    raise RuntimeError(
        f"None of the top {CANDIDATES_TO_CHECK} candidate WUI polygons had "
        f">= {MIN_VALID_FRACTION:.0%} real LiDAR coverage - widen the search."
    )


def main() -> None:
    print("Fetching unincorporated King County boundary...")
    cities = fetch_layer(CITIES_URL, where="JURIS='KC'")
    unincorporated_main = cities.loc[cities.area.idxmax(), "geometry"]
    print(f"  Main unincorporated polygon area: {unincorporated_main.area / 5280**2:.0f} sq mi")

    print("Fetching Wildland Urban Interface polygons...")
    wui = fetch_layer(WUI_URL)
    print(f"  {len(wui)} WUI features fetched")

    # King County's WUI layer has some invalid (self-intersecting) polygons
    # - the same class of issue kc-data-quality-audit's geometry_validity
    # check flags elsewhere in their catalog. make_valid() before any
    # intersection op, or GEOS raises TopologyException.
    wui["geometry"] = wui.geometry.make_valid()
    wui_in_unincorporated = wui[wui.intersects(unincorporated_main)].copy()
    print(f"  {len(wui_in_unincorporated)} WUI features intersect unincorporated King County")

    tile_overlaps = {}
    for tile_name in DEM_TILES:
        tile_url = f"{DEM_BASE}{tile_name}"
        with rasterio.open(f"/vsicurl/{tile_url}") as src:
            tile_box = box(*src.bounds)

        overlap = wui_in_unincorporated[wui_in_unincorporated.intersects(tile_box)].copy()
        if overlap.empty:
            print(f"  {tile_name}: no WUI-in-unincorporated overlap")
            continue

        overlap["clipped_area"] = overlap.geometry.intersection(tile_box).area
        total_overlap_area = overlap["clipped_area"].sum()
        print(f"  {tile_name}: {len(overlap)} overlapping WUI polygons, "
              f"{total_overlap_area / 5280**2:.1f} sq mi total overlap")
        tile_overlaps[tile_name] = {"tile_url": tile_url, "tile_box": tile_box,
                                     "overlap": overlap, "total_area": total_overlap_area}

    if not tile_overlaps:
        raise RuntimeError("No DEM tile overlaps WUI-in-unincorporated area - check inputs.")

    # Try tiles largest-overlap-first; a tile can rank #1 by area but still
    # fail if its top candidates all land on data gaps, so fall through.
    ranked_tiles = sorted(tile_overlaps.items(), key=lambda kv: -kv[1]["total_area"])
    anchor_x = anchor_y = chosen_tile = None
    for tile_name, info in ranked_tiles:
        print(f"\nChecking real pixel coverage in {tile_name}...")
        with rasterio.open(f"/vsicurl/{info['tile_url']}") as src:
            try:
                anchor_x, anchor_y = pick_valid_anchor(src, info["overlap"], info["tile_box"])
                chosen_tile = tile_name
                break
            except RuntimeError as exc:
                print(f"  {exc}")

    if chosen_tile is None:
        raise RuntimeError("No candidate AOI in any overlapping tile had real LiDAR coverage.")

    best = {"tile_name": chosen_tile, "tile_url": tile_overlaps[chosen_tile]["tile_url"]}
    clip_bbox = (
        anchor_x - CLIP_HALF_WIDTH_FT,
        anchor_y - CLIP_HALF_WIDTH_FT,
        anchor_x + CLIP_HALF_WIDTH_FT,
        anchor_y + CLIP_HALF_WIDTH_FT,
    )

    result = {
        "tile_name": best["tile_name"],
        "tile_url": best["tile_url"],
        "crs_epsg": CRS_EPSG,
        "anchor_point_ft": [anchor_x, anchor_y],
        "clip_bbox_ft": list(clip_bbox),
        "clip_bbox_note": "minx, miny, maxx, maxy in EPSG:2926 (US survey feet)",
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nSelected tile: {best['tile_name']}")
    print(f"Clip bbox (EPSG:2926 ft): {clip_bbox}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
