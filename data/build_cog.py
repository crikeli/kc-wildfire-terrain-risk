"""
Phase 3: clip the selected AOI out of the remote King County LiDAR DEM
(windowed read only - see benchmark_access.py for how little of the 1.35 GB
source file this actually touches) and write it as our own small,
spec-validated COG - the base layer everything downstream (terrain
analysis, STAC catalog, the web viewer) builds on.

Usage:
    python build_cog.py
"""

import json
import os

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
AOI_PATH = os.path.join(DATA_DIR, "aoi_selection.json")
SCRATCH_PATH = os.path.join(DATA_DIR, "scratch", "dem_aoi_raw.tif")
COG_DIR = os.path.join(os.path.dirname(DATA_DIR), "docs", "cogs")  # published by GitHub Pages
COG_PATH = os.path.join(COG_DIR, "dem_aoi.tif")


def main() -> None:
    with open(AOI_PATH) as f:
        aoi = json.load(f)

    minx, miny, maxx, maxy = aoi["clip_bbox_ft"]
    vsi_url = f"/vsicurl/{aoi['tile_url']}"

    os.makedirs(os.path.dirname(SCRATCH_PATH), exist_ok=True)
    os.makedirs(COG_DIR, exist_ok=True)

    print(f"Reading AOI window from {aoi['tile_url']} (windowed - not a full download)...")
    with rasterio.open(vsi_url) as src:
        window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        data = src.read(1, window=window)
        transform = src.window_transform(window)
        profile = src.profile.copy()
        nodata = src.nodata

    profile.update(
        height=data.shape[0],
        width=data.shape[1],
        transform=transform,
        tiled=True,
        compress="deflate",
    )
    with rasterio.open(SCRATCH_PATH, "w", **profile) as dst:
        dst.write(data, 1)

    print(f"Converting to COG: {COG_PATH}")
    # predictor=3 (floating-point differencing) matters a lot here - the
    # deflate profile doesn't set one by default, and without it deflate
    # barely compresses continuous elevation data.
    profile = cog_profiles.get("deflate")
    profile.update(predictor=3)
    cog_translate(
        SCRATCH_PATH,
        COG_PATH,
        profile,
        overview_resampling="average",
        forward_band_tags=True,
        nodata=nodata,
        quiet=True,
    )

    is_valid, errors, warnings = cog_validate(COG_PATH, strict=True)
    print(f"cog_validate on our output: is_valid={is_valid}, errors={errors}, warnings={warnings}")
    if not is_valid:
        raise RuntimeError(f"Our own COG output failed validation: {errors}")

    valid_pixels = data[data != nodata] if nodata is not None else data
    print(f"\nAOI raster: {data.shape[1]}x{data.shape[0]} px, "
          f"elevation range {np.nanmin(valid_pixels):.1f}-{np.nanmax(valid_pixels):.1f} ft")
    print(f"Wrote {COG_PATH} ({os.path.getsize(COG_PATH) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
