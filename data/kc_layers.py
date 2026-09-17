"""
Shared config + fetch helper for the handful of King County vector layers
this project needs. Unlike kc-data-quality-audit (which audits ~18 layers
from the full DCAT catalog), this project only needs these four specific,
already-identified layers, so there's no need to re-fetch the whole
catalog - titles/URLs below were resolved once against
kc-data-quality-audit's catalog.parquet and are pinned here.

All layers are queried in EPSG:2926 (NAD83(HARN) / Washington North, US
feet) - the same horizontal CRS the King County LiDAR DEM tiles use - so
vector and raster data line up without extra reprojection.
"""

import geopandas as gpd
import requests

WUI_URL = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/WILDLAND_URBAN_INTERFACE_AREA_2923/FeatureServer/0"
FIRE_STATIONS_URL = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/FIRESTN_POINT_98/FeatureServer/0"
FIRE_DISTRICTS_URL = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/FIRDST_AREA_407/FeatureServer/0"
CITIES_URL = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/CITY_KC_AREA_446/FeatureServer/0"

CRS_EPSG = 2926


def fetch_layer(url: str, where: str = "1=1", out_fields: str = "*", bbox: tuple | None = None) -> gpd.GeoDataFrame:
    """Fetches all features from an ArcGIS FeatureServer layer, paginating
    via resultOffset until exceededTransferLimit is no longer set.

    `bbox`, if given, is (minx, miny, maxx, maxy) in EPSG:2926 and is
    applied as a proper ArcGIS REST spatial filter (geometry/geometryType/
    spatialRel), not a WHERE-clause hack - SHAPE.STX/STY-style predicates
    are provider-specific and not reliable across ArcGIS Online services.
    """
    features = []
    offset = 0
    params_base = {
        "where": where,
        "outFields": out_fields,
        "f": "geojson",
        "outSR": CRS_EPSG,
    }
    if bbox is not None:
        params_base.update({
            "geometry": ",".join(str(v) for v in bbox),
            "geometryType": "esriGeometryEnvelope",
            "inSR": CRS_EPSG,
            "spatialRel": "esriSpatialRelIntersects",
        })

    while True:
        resp = requests.get(
            f"{url}/query",
            params={**params_base, "resultOffset": offset},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            raise ValueError(f"ArcGIS query error for {url}: {payload['error']}")
        batch = payload.get("features", [])
        features.extend(batch)
        if not payload.get("properties", {}).get("exceededTransferLimit") and len(batch) == 0:
            break
        if not payload.get("properties", {}).get("exceededTransferLimit"):
            break
        offset += len(batch)

    return gpd.GeoDataFrame.from_features(features, crs=f"EPSG:{CRS_EPSG}")
