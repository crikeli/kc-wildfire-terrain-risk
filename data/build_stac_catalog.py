"""
Phase 6: a minimal static STAC catalog describing the DEM and every
derived COG - the actual current standard for cataloging cloud-native
geospatial assets, not an ad hoc filename convention. Written as static
JSON files (Catalog -> Collection -> Item), browsable with any STAC client.

Usage:
    python build_stac_catalog.py
"""

import os
from datetime import datetime, timezone

import pystac
import rioxarray
from pyproj import Transformer

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(os.path.dirname(DATA_DIR), "docs")
COG_DIR = os.path.join(DOCS_DIR, "cogs")  # published by GitHub Pages
STAC_DIR = os.path.join(DOCS_DIR, "stac")

ASSETS = {
    "dem_aoi.tif": ("elevation", "King County 2016 LiDAR bare-earth DEM (AOI clip)"),
    "slope.tif": ("slope", "Slope (degrees), derived via xarray-spatial"),
    "aspect.tif": ("aspect", "Aspect (degrees), derived via xarray-spatial"),
    "hillshade.tif": ("hillshade", "Hillshade, derived via xarray-spatial"),
    "distance_to_fire_station.tif": ("distance", "Distance to nearest fire station (ft)"),
    "terrain_risk_index.tif": ("risk", "Illustrative composite terrain risk index (0-1)"),
}
COG_MEDIA_TYPE = "image/tiff; application=geotiff; profile=cloud-optimized"


def wgs84_bbox_and_geometry(cog_path: str):
    da = rioxarray.open_rasterio(cog_path)
    bounds = da.rio.bounds()
    transformer = Transformer.from_crs(da.rio.crs, "EPSG:4326", always_xy=True)
    minx, miny = transformer.transform(bounds[0], bounds[1])
    maxx, maxy = transformer.transform(bounds[2], bounds[3])
    bbox = [minx, miny, maxx, maxy]
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny],
        ]],
    }
    return bbox, geometry


def main() -> None:
    os.makedirs(STAC_DIR, exist_ok=True)

    dem_path = os.path.join(COG_DIR, "dem_aoi.tif")
    bbox, geometry = wgs84_bbox_and_geometry(dem_path)

    catalog = pystac.Catalog(
        id="kc-wildfire-terrain-risk",
        description=(
            "Cloud-Optimized GeoTIFF assets for a terrain-based wildfire "
            "exposure demonstration in unincorporated King County, WA. "
            "Source DEM: King County 2016 LiDAR bare-earth (NOAA Digital "
            "Coast). Illustrative only - see the project README."
        ),
        title="King County Wildfire Terrain Risk - AOI Assets",
    )

    collection = pystac.Collection(
        id="wildfire-terrain-aoi",
        description="Derived terrain rasters for one AOI in the Cascade foothills of unincorporated King County",
        extent=pystac.Extent(
            spatial=pystac.SpatialExtent([bbox]),
            temporal=pystac.TemporalExtent([[datetime(2016, 1, 1, tzinfo=timezone.utc), None]]),
        ),
        license="proprietary",
    )
    catalog.add_child(collection)

    item = pystac.Item(
        id="wildfire-terrain-aoi-item",
        geometry=geometry,
        bbox=bbox,
        datetime=datetime(2016, 1, 1, tzinfo=timezone.utc),
        properties={
            "description": "AOI DEM and derived terrain-risk layers",
            "source": "King County 2016 LiDAR bare-earth DEM, via NOAA Digital Coast",
        },
    )
    for filename, (key, title) in ASSETS.items():
        item.add_asset(
            key,
            pystac.Asset(
                href=f"../../../cogs/{filename}",  # item dir -> collection -> stac -> docs -> cogs
                title=title,
                media_type=COG_MEDIA_TYPE,
                roles=["data"],
            ),
        )
    collection.add_item(item)

    catalog.normalize_hrefs(STAC_DIR)
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

    print(f"Wrote STAC catalog to {STAC_DIR}")
    print("Item asset hrefs point to docs/cogs/*.tif (relative)")


if __name__ == "__main__":
    main()
