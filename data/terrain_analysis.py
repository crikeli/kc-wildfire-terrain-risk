"""
Phase 4: terrain analysis on the AOI COG via xarray-spatial - slope,
aspect, hillshade, and a distance-to-nearest-fire-station surface - combined
into an explicitly illustrative composite terrain risk index.

This is NOT a fuel-moisture/weather/vegetation-type wildfire risk model and
NOT a replacement for King County's official Wildland Urban Interface
designation - see README.md. It's a terrain-only demonstration: steeper
slopes carry fire faster, south/west-facing slopes run hotter and drier in
the Northern Hemisphere, and distance to the nearest fire station is a
crude response-time proxy. The weights below are illustrative, not
calibrated against any real fire-behavior model.

Usage:
    python terrain_analysis.py
"""

import os

import numpy as np
import rioxarray
import xarray as xr
from xrspatial import aspect, hillshade, slope

from kc_layers import FIRE_STATIONS_URL, fetch_layer

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
COG_DIR = os.path.join(os.path.dirname(DATA_DIR), "docs", "cogs")  # published by GitHub Pages
DEM_PATH = os.path.join(COG_DIR, "dem_aoi.tif")

# Illustrative composite weights - see module docstring. Not calibrated.
WEIGHT_SLOPE = 0.5
WEIGHT_SOUTHWESTNESS = 0.3
WEIGHT_DISTANCE_TO_STATION = 0.2
STATION_SEARCH_BUFFER_FT = 30_000  # ~5.7 miles - wide enough to find the nearest station(s)
DISTANCE_CAP_FT = 26_400  # 5 miles - beyond this, "distance risk" is treated as maxed out


def min_max_normalize(arr: np.ndarray) -> np.ndarray:
    valid = np.isfinite(arr)
    lo, hi = np.nanmin(arr[valid]), np.nanmax(arr[valid])
    if hi == lo:
        return np.zeros_like(arr)
    return np.clip((arr - lo) / (hi - lo), 0, 1)


def write_cog(data_array: xr.DataArray, path: str, predictor: int = 3) -> None:
    # predictor=3 (floating-point) or 2 (horizontal differencing, for
    # integer data) makes deflate compression much more effective on smooth
    # continuous surfaces - without it these files were 2-3x larger.
    data_array.rio.to_raster(
        path, driver="COG", compress="deflate", predictor=predictor, overview_resampling="average",
    )


def main() -> None:
    dem = rioxarray.open_rasterio(DEM_PATH, masked=True).squeeze("band", drop=True)
    dem.name = "elevation"

    print("Computing slope, aspect, hillshade...")
    slope_da = slope(dem)
    aspect_da = aspect(dem)
    # xarray-spatial's hillshade() returns a normalized 0-1 float64 - scale
    # to the conventional 0-255 range before casting to uint8. (Casting the
    # raw 0-1 float straight to uint8 truncates everything to 0 - caught
    # this from a first pass that produced an all-zero raster.)
    hillshade_da = (hillshade(dem) * 255).round().fillna(0).astype("uint8")

    write_cog(slope_da, os.path.join(COG_DIR, "slope.tif"))
    write_cog(aspect_da, os.path.join(COG_DIR, "aspect.tif"))
    write_cog(hillshade_da, os.path.join(COG_DIR, "hillshade.tif"), predictor=2)

    minx, miny, maxx, maxy = dem.rio.bounds()
    search_bounds = (minx - STATION_SEARCH_BUFFER_FT, miny - STATION_SEARCH_BUFFER_FT,
                      maxx + STATION_SEARCH_BUFFER_FT, maxy + STATION_SEARCH_BUFFER_FT)
    print("Fetching nearby fire stations...")
    stations = fetch_layer(FIRE_STATIONS_URL, bbox=search_bounds)
    print(f"  {len(stations)} fire stations found within the search buffer")

    # xarray-spatial's proximity() only measures distance to target cells
    # that fall INSIDE the raster grid - not useful here, since this AOI is
    # a ~2km clip and the nearest station is very likely outside it
    # entirely. Plain vectorized per-pixel Euclidean distance to the real
    # station coordinates (whether inside the clip or not) is the correct
    # tool for this, not a grid-internal proximity transform.
    xx, yy = np.meshgrid(dem.x.values, dem.y.values)
    if len(stations) == 0:
        print("  No fire stations found even within the search buffer - distance surface "
              "left at the capped max (uniform, honestly reported rather than fabricated).")
        distance_ft = np.full(xx.shape, DISTANCE_CAP_FT, dtype=np.float32)
    else:
        distance_ft = np.full(xx.shape, np.inf, dtype=np.float64)
        for geom in stations.geometry:
            d = np.sqrt((xx - geom.x) ** 2 + (yy - geom.y) ** 2)
            distance_ft = np.minimum(distance_ft, d)
        distance_ft = distance_ft.astype(np.float32)

    distance_da_out = xr.DataArray(distance_ft, dims=dem.dims[-2:], coords={"y": dem.y, "x": dem.x})
    distance_da_out = distance_da_out.rio.write_crs(dem.rio.crs).rio.write_transform(dem.rio.transform())
    write_cog(distance_da_out, os.path.join(COG_DIR, "distance_to_fire_station.tif"))

    print("Building composite terrain risk index (illustrative weights, see docstring)...")
    slope_norm = min_max_normalize(slope_da.data)
    aspect_arr = aspect_da.data
    southwestness = (np.cos(np.radians(aspect_arr - 225)) + 1) / 2
    southwestness = np.where(aspect_arr < 0, 0.5, southwestness)  # flat cells -> neutral
    distance_capped = np.clip(distance_ft, 0, DISTANCE_CAP_FT)
    distance_norm = distance_capped / DISTANCE_CAP_FT

    risk = (
        WEIGHT_SLOPE * slope_norm
        + WEIGHT_SOUTHWESTNESS * southwestness
        + WEIGHT_DISTANCE_TO_STATION * distance_norm
    )
    risk_da = xr.DataArray(risk.astype("float32"), dims=dem.dims[-2:], coords={"y": dem.y, "x": dem.x})
    risk_da = risk_da.rio.write_crs(dem.rio.crs).rio.write_transform(dem.rio.transform())
    write_cog(risk_da, os.path.join(COG_DIR, "terrain_risk_index.tif"))

    print(f"\nSlope range: {np.nanmin(slope_da.data):.1f}-{np.nanmax(slope_da.data):.1f} deg")
    print(f"Distance to nearest fire station: {np.nanmin(distance_ft) / 5280:.1f}-"
          f"{np.nanmax(distance_ft) / 5280:.1f} mi across the AOI")
    print(f"Composite risk index range: {np.nanmin(risk):.2f}-{np.nanmax(risk):.2f} (0-1 scale)")
    print("Wrote slope.tif, aspect.tif, hillshade.tif, distance_to_fire_station.tif, "
          f"terrain_risk_index.tif to {COG_DIR}")


if __name__ == "__main__":
    main()
