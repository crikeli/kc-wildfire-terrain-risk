"""
Phase 5: the "useful to King County" payoff. Compares the terrain-only
risk index against King County's own official Wildland Urban Interface
(WUI) designation for the same AOI - not to second-guess the county's
designation (WUI incorporates far more than terrain - structure density,
vegetation, access, and local fire-behavior expertise), but to report,
honestly, where a purely terrain-based lens agrees or diverges from it.
That divergence is the actual finding, in the same spirit as the
tree-canopy-family finding in kc-data-quality-audit - not "the county is
wrong," but "here's a concrete, reproducible gap worth a human look."

Usage:
    python compare_to_wui.py
"""

import json
import os

import numpy as np
import rioxarray
from rasterio.features import rasterize

from kc_layers import WUI_URL, fetch_layer

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
COG_DIR = os.path.join(os.path.dirname(DATA_DIR), "docs", "cogs")  # published by GitHub Pages
RISK_PATH = os.path.join(COG_DIR, "terrain_risk_index.tif")
OUTPUT_PATH = os.path.join(DATA_DIR, "wui_comparison.json")

HIGH_RISK_PERCENTILE = 75  # top quartile of THIS AOI's own risk distribution, not an absolute cutoff


def main() -> None:
    risk = rioxarray.open_rasterio(RISK_PATH, masked=True).squeeze("band", drop=True)

    minx, miny, maxx, maxy = risk.rio.bounds()
    print("Fetching WUI polygons for this AOI...")
    wui = fetch_layer(WUI_URL, bbox=(minx, miny, maxx, maxy))
    wui["geometry"] = wui.geometry.make_valid()
    print(f"  {len(wui)} WUI polygon(s) intersect this AOI")

    wui_mask = np.zeros(risk.shape, dtype=bool)
    if len(wui):
        shapes = [(geom, 1) for geom in wui.geometry if geom is not None and not geom.is_empty]
        if shapes:
            wui_mask = rasterize(
                shapes, out_shape=risk.shape, transform=risk.rio.transform(), fill=0, dtype=np.uint8,
            ).astype(bool)

    risk_arr = risk.data
    valid = np.isfinite(risk_arr)
    threshold = np.percentile(risk_arr[valid], HIGH_RISK_PERCENTILE)
    high_risk_mask = valid & (risk_arr >= threshold)

    total_valid = valid.sum()
    total_high_risk = high_risk_mask.sum()
    total_wui = (wui_mask & valid).sum()

    high_risk_in_wui = (high_risk_mask & wui_mask).sum()
    high_risk_outside_wui = (high_risk_mask & ~wui_mask).sum()
    wui_that_is_high_risk = (wui_mask & valid & high_risk_mask).sum()

    result = {
        "high_risk_percentile_threshold": HIGH_RISK_PERCENTILE,
        "risk_threshold_value": float(threshold),
        "total_valid_cells": int(total_valid),
        "total_high_risk_cells": int(total_high_risk),
        "total_official_wui_cells": int(total_wui),
        "pct_high_risk_cells_inside_official_wui": (
            round(100 * high_risk_in_wui / total_high_risk, 1) if total_high_risk else None
        ),
        "pct_high_risk_cells_outside_official_wui": (
            round(100 * high_risk_outside_wui / total_high_risk, 1) if total_high_risk else None
        ),
        "pct_official_wui_cells_flagged_high_risk": (
            round(100 * wui_that_is_high_risk / total_wui, 1) if total_wui else None
        ),
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nHigh-risk threshold (this AOI's own {HIGH_RISK_PERCENTILE}th percentile): "
          f"{threshold:.2f}")
    print(f"Official WUI covers {100 * total_wui / total_valid:.1f}% of this AOI")
    if total_high_risk:
        print(f"{result['pct_high_risk_cells_inside_official_wui']}% of terrain-flagged "
              f"high-risk cells fall inside the official WUI boundary")
        print(f"{result['pct_high_risk_cells_outside_official_wui']}% fall outside it - "
              "the terrain-only signal reaching beyond the official designation")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
