"""
Phase 2: the efficiency showcase.

Original assumption going into this project was "King County's published
LiDAR DEM probably isn't a Cloud-Optimized GeoTIFF - convert it and measure
the improvement." That assumption turned out to be **wrong**, and this
script reports the real finding instead of a fabricated one:
`rio_cogeo.cog_validate()` confirms the actual NOAA-hosted King County DEM
tile is already a valid, spec-compliant COG (internally tiled in 512x512
blocks with a full overview pyramid). That's a genuinely good sign for
King County's data practices, worth reporting honestly rather than
overwritten with a "before/after conversion" story that isn't true.

What this script demonstrates instead - real, measured, on the live file:
how much of a 1.35 GB remote raster a single small-AOI windowed read
actually has to touch, thanks to that COG structure. No download of the
full file at any point - only the header (already done in select_aoi.py)
and the specific blocks needed for the AOI window.

Usage:
    python benchmark_access.py
"""

import json
import math
import os
import time

import rasterio
import requests
from rasterio.windows import from_bounds
from rio_cogeo.cogeo import cog_validate

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
AOI_PATH = os.path.join(DATA_DIR, "aoi_selection.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "benchmark_results.json")


def main() -> None:
    with open(AOI_PATH) as f:
        aoi = json.load(f)

    tile_url = aoi["tile_url"]
    vsi_url = f"/vsicurl/{tile_url}"
    minx, miny, maxx, maxy = aoi["clip_bbox_ft"]

    print(f"Validating COG compliance of the live remote file: {tile_url}")
    is_valid, errors, warnings = cog_validate(vsi_url, strict=True)
    print(f"  cog_validate: is_valid={is_valid}, errors={errors}, warnings={warnings}")

    file_size_bytes = int(requests.head(tile_url, timeout=30).headers["Content-Length"])

    with rasterio.open(vsi_url) as src:
        assert src.is_tiled, "Expected a tiled GeoTIFF - AOI selection assumptions no longer hold."
        block_w, block_h = src.block_shapes[0]
        total_blocks = math.ceil(src.width / block_w) * math.ceil(src.height / block_h)

        window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)

        start = time.perf_counter()
        data = src.read(1, window=window)
        elapsed_seconds = time.perf_counter() - start

        col_start = math.floor(window.col_off / block_w)
        col_end = math.ceil((window.col_off + window.width) / block_w)
        row_start = math.floor(window.row_off / block_h)
        row_end = math.ceil((window.row_off + window.height) / block_h)
        blocks_touched = (col_end - col_start) * (row_end - row_start)

    pct_touched = 100 * blocks_touched / total_blocks
    window_pixels = data.size
    window_bytes_raw = window_pixels * data.dtype.itemsize

    result = {
        "tile_url": tile_url,
        "is_valid_cog": is_valid,
        "cog_errors": errors,
        "cog_warnings": warnings,
        "file_size_bytes": file_size_bytes,
        "block_shape": [block_w, block_h],
        "total_blocks": total_blocks,
        "blocks_touched_by_aoi_window": blocks_touched,
        "pct_of_file_blocks_touched": round(pct_touched, 4),
        "window_read_seconds": round(elapsed_seconds, 3),
        "window_pixel_count": window_pixels,
        "window_raw_bytes_uncompressed": window_bytes_raw,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nFile size: {file_size_bytes / 1e6:.1f} MB")
    print(f"Total blocks in file: {total_blocks}")
    print(f"Blocks touched by this AOI's windowed read: {blocks_touched} "
          f"({pct_touched:.3f}% of the file)")
    print(f"Windowed read took {elapsed_seconds:.2f}s over the network for "
          f"{window_bytes_raw / 1e6:.1f} MB of pixel data")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
