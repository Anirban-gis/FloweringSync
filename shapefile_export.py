"""
==========================================================
Flowering Synchronisation Analysis Tool
shapefile_export.py - Export synchronized plot pairs as a shapefile

Produces line geometries connecting each isolation plot's centroid
to each synchronized surrounding plot's centroid, carrying the
key attributes, so results can be visualized directly in
QGIS / ArcGIS.
==========================================================
"""

import geopandas as gpd
from shapely.geometry import LineString


def export_sync_shapefile(results, iso_gdf, sur_gdf, iso_fields, sur_fields, output_path):
    """
    results : list of dict rows from the analysis engine
    iso_gdf, sur_gdf : original GeoDataFrames (same CRS)
    iso_fields, sur_fields : dict with 'id' key mapping to the ID column
    output_path : path to output .shp
    """
    iso_id_f = iso_fields["id"]
    sur_id_f = sur_fields["id"]

    # Build quick lookup: id (as string) -> centroid geometry
    iso_lookup = {
        str(row[iso_id_f]): row.geometry.centroid
        for _, row in iso_gdf.iterrows()
    } if iso_id_f else {}

    sur_lookup = {
        str(row[sur_id_f]): row.geometry.centroid
        for _, row in sur_gdf.iterrows()
    } if sur_id_f else {}

    features = []
    for r in results:
        if r.get("Remarks") != "Crop Flowering Sync":
            continue

        iso_id = str(r["Isolation_ID"])
        sur_id = str(r["Surrounding_ID"])

        iso_pt = iso_lookup.get(iso_id)
        sur_pt = sur_lookup.get(sur_id)

        if iso_pt is None or sur_pt is None:
            continue

        line = LineString([iso_pt, sur_pt])

        features.append({
            "Iso_ID": r["Isolation_ID"],
            "Sur_ID": r["Surrounding_ID"],
            "Iso_Crop": r["Isolation_Crop"],
            "Sur_Crop": r["Surrounding_Crop"],
            "Distance_m": r["Distance_m"],
            "OverlapDay": r["Overlap_Days"],
            "Remarks": r["Remarks"],
            "geometry": line,
        })

    if not features:
        gdf = gpd.GeoDataFrame(
            columns=["Iso_ID", "Sur_ID", "Iso_Crop", "Sur_Crop",
                     "Distance_m", "OverlapDay", "Remarks", "geometry"],
            geometry="geometry",
            crs=iso_gdf.crs,
        )
    else:
        gdf = gpd.GeoDataFrame(features, geometry="geometry", crs=iso_gdf.crs)

    gdf.to_file(output_path)
    return output_path
