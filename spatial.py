"""
==========================================================
Flowering Synchronisation Analysis Tool
spatial.py - Spatial indexing and distance calculations
==========================================================
"""

import geopandas as gpd

try:
    from rtree import index as rtree_index
    HAS_RTREE = True
except Exception:
    HAS_RTREE = False


def check_crs(iso_gdf, sur_gdf):
    """
    Validate that both layers share the same CRS and that the CRS is
    projected (i.e. in meters, not degrees).

    Returns (ok: bool, message: str)
    """
    if iso_gdf.crs is None or sur_gdf.crs is None:
        return False, "One or both layers have no CRS defined."

    if iso_gdf.crs != sur_gdf.crs:
        return False, "Isolation and Surrounding layers have different CRS."

    try:
        if iso_gdf.crs.is_geographic:
            return False, (
                "Layers are in a Geographic CRS (degrees). "
                "Distance calculation requires a Projected CRS (meters)."
            )
    except Exception:
        pass

    return True, "CRS OK"


def build_spatial_index(gdf):
    """
    Build a spatial index over the bounding boxes of a GeoDataFrame's
    geometries. Uses rtree if available (fast), otherwise falls back
    to GeoPandas' built-in sindex.
    """
    if HAS_RTREE:
        idx = rtree_index.Index()
        for pos, geom in enumerate(gdf.geometry):
            if geom is not None and not geom.is_empty:
                idx.insert(pos, geom.bounds)
        return idx
    else:
        # GeoPandas' own spatial index (pygeos/shapely STRtree based)
        return gdf.sindex


def query_nearby(index, gdf, geom, distance):
    """
    Given a spatial index built with build_spatial_index(), the
    GeoDataFrame it was built from, a query geometry, and a search
    distance (in the same units as the CRS, i.e. meters), return a
    list of integer positional indices of candidate features whose
    bounding box (expanded by `distance`) intersects the query
    geometry's expanded bounding box.

    This is a coarse pre-filter; exact distance is computed
    afterwards with Shapely.
    """
    minx, miny, maxx, maxy = geom.bounds
    expanded = (minx - distance, miny - distance, maxx + distance, maxy + distance)

    if HAS_RTREE:
        return list(index.intersection(expanded))
    else:
        # gdf.sindex.query with a buffered box via bbox intersection
        possible = list(index.intersection(expanded))
        return possible


def edge_to_edge_distance(geom_a, geom_b):
    """Minimum edge-to-edge distance between two geometries (meters)."""
    return geom_a.distance(geom_b)


def centroid_distance(geom_a, geom_b):
    """Centroid-to-centroid distance between two geometries (meters)."""
    return geom_a.centroid.distance(geom_b.centroid)


def compute_distance(geom_a, geom_b, method="centroid"):
    """
    method: 'centroid' or 'edge'
    """
    if method == "edge":
        return edge_to_edge_distance(geom_a, geom_b)
    return centroid_distance(geom_a, geom_b)
