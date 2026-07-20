"""
==========================================================
Flowering Synchronisation Analysis Tool
analysis.py - Core analysis engine

Implements the decision logic:

  Crop Match | Distance OK | Flower Overlap | Remarks
  No         | -           | -              | Other Crop
  Yes        | No          | -              | Outside Distance
  Yes        | Yes         | 0              | No Flower Synchronisation
  Yes        | Yes         | >0             | Crop Flowering Sync
==========================================================
"""

from utils import parse_date, safe_str, crops_match, format_date
from spatial import build_spatial_index, query_nearby, compute_distance


class FloweringSynchronisation:
    """
    Runs the isolation-vs-surrounding flowering synchronisation analysis.

    Parameters
    ----------
    iso_gdf, sur_gdf : GeoDataFrame
        Loaded isolation / surrounding plot layers (same CRS, projected).
    iso_fields, sur_fields : dict
        Each dict has keys: id, crop, start, end  -> column names.
    crop_compare : str
        Crop name to filter on. If empty, all crop matches are allowed
        (isolation crop must equal surrounding crop).
    distance_limit : float
        Maximum proximity distance in meters.
    distance_method : str
        'centroid' or 'edge'
    progress_callback : callable(percent:int, message:str) or None
    log_callback : callable(message:str) or None
    """

    def __init__(
        self,
        iso_gdf,
        sur_gdf,
        iso_fields,
        sur_fields,
        crop_compare,
        distance_limit,
        distance_method="centroid",
        progress_callback=None,
        log_callback=None,
    ):
        self.iso_gdf = iso_gdf.reset_index(drop=True)
        self.sur_gdf = sur_gdf.reset_index(drop=True)
        self.iso_fields = iso_fields
        self.sur_fields = sur_fields
        self.crop_compare = safe_str(crop_compare)
        self.distance_limit = float(distance_limit)
        self.distance_method = distance_method
        self.progress_callback = progress_callback or (lambda pct, msg: None)
        self.log_callback = log_callback or (lambda msg: None)

        self.results = []          # list of dict rows (all comparisons)
        self.stats = {}            # summary statistics

    # ------------------------------------------------------------
    def _progress(self, pct, msg=""):
        self.progress_callback(pct, msg)

    def _log(self, msg):
        self.log_callback(msg)

    # ------------------------------------------------------------
    def run(self):
        self._progress(5, "Preparing data...")
        self._log("-" * 50)
        self._log(f"Isolation plots loaded : {len(self.iso_gdf)}")
        self._log(f"Surrounding plots loaded : {len(self.sur_gdf)}")

        iso_id_f = self.iso_fields["id"]
        iso_crop_f = self.iso_fields["crop"]
        iso_start_f = self.iso_fields["start"]
        iso_end_f = self.iso_fields["end"]

        sur_id_f = self.sur_fields["id"]
        sur_crop_f = self.sur_fields["crop"]
        sur_start_f = self.sur_fields["start"]
        sur_end_f = self.sur_fields["end"]

        self._progress(20, "Building spatial index...")
        sindex = build_spatial_index(self.sur_gdf)
        self._log("Spatial index created.")

        total = len(self.iso_gdf)
        other_crop = 0
        outside_distance = 0
        no_overlap = 0
        synced = 0
        overlap_days_list = []

        for pos, iso_row in self.iso_gdf.iterrows():
            pct = 20 + int(70 * (pos + 1) / max(total, 1))
            self._progress(pct, f"Checking Isolation Plot {pos + 1}/{total}...")

            iso_id = safe_str(iso_row.get(iso_id_f, pos)) if iso_id_f else str(pos)
            iso_crop = safe_str(iso_row.get(iso_crop_f, ""))
            iso_start = parse_date(iso_row.get(iso_start_f))
            iso_end = parse_date(iso_row.get(iso_end_f))
            iso_geom = iso_row.geometry

            self._log(f"Checking Plot ID {iso_id}...")

            if iso_geom is None or iso_geom.is_empty:
                self._log("  Skipped (invalid geometry).")
                continue

            candidate_positions = query_nearby(
                sindex, self.sur_gdf, iso_geom, self.distance_limit
            )

            if not candidate_positions:
                self._log("  No nearby plots found.")
                continue

            self._log(f"  {len(candidate_positions)} neighbouring plot(s) found.")

            for spos in candidate_positions:
                sur_row = self.sur_gdf.iloc[spos]
                sur_geom = sur_row.geometry
                if sur_geom is None or sur_geom.is_empty:
                    continue

                sur_id = safe_str(sur_row.get(sur_id_f, spos)) if sur_id_f else str(spos)
                sur_crop = safe_str(sur_row.get(sur_crop_f, ""))
                sur_start = parse_date(sur_row.get(sur_start_f))
                sur_end = parse_date(sur_row.get(sur_end_f))

                # Skip comparing a plot to itself if same layer/ID coincidentally
                # (not required, but harmless safety check omitted intentionally)

                # Step 2: Crop check ------------------------------------------------
                target_crop = self.crop_compare if self.crop_compare else iso_crop
                crop_ok = crops_match(iso_crop, target_crop) and crops_match(
                    sur_crop, target_crop
                )
                # If no specific crop filter given, just require iso_crop == sur_crop
                if not self.crop_compare:
                    crop_ok = crops_match(iso_crop, sur_crop)

                if not crop_ok:
                    other_crop += 1
                    self.results.append(self._row(
                        iso_id, iso_crop, iso_start, iso_end,
                        sur_id, sur_crop, sur_start, sur_end,
                        None, "No", "No", None, None, None,
                        "Other Crop"
                    ))
                    continue

                # Step 1: Distance ---------------------------------------------------
                distance = compute_distance(iso_geom, sur_geom, self.distance_method)

                if distance > self.distance_limit:
                    outside_distance += 1
                    self.results.append(self._row(
                        iso_id, iso_crop, iso_start, iso_end,
                        sur_id, sur_crop, sur_start, sur_end,
                        distance, "Yes", "No", None, None, None,
                        "Outside Distance"
                    ))
                    continue

                self._log(f"    Plot {sur_id} | Crop: {sur_crop} | Distance: {distance:.1f} m")

                # Step 3: Flowering overlap ------------------------------------------
                overlap_start = overlap_end = None
                overlap_days = 0

                if iso_start and iso_end and sur_start and sur_end:
                    overlap_start = max(iso_start, sur_start)
                    overlap_end = min(iso_end, sur_end)
                    delta = (overlap_end - overlap_start).days + 1
                    overlap_days = delta if delta > 0 else 0

                if overlap_days <= 0:
                    no_overlap += 1
                    remarks = "No Flower Synchronisation"
                    self._log("    Flower Overlap: 0 days -> No Flower Synchronisation")
                else:
                    synced += 1
                    overlap_days_list.append(overlap_days)
                    remarks = "Crop Flowering Sync"
                    self._log(f"    Flower Overlap: {overlap_days} days -> Crop Flowering Sync")

                self.results.append(self._row(
                    iso_id, iso_crop, iso_start, iso_end,
                    sur_id, sur_crop, sur_start, sur_end,
                    distance, "Yes", "Yes" if overlap_days > 0 else "No",
                    overlap_start, overlap_end, overlap_days,
                    remarks
                ))

        self._progress(95, "Finalising results...")

        self.stats = {
            "Total isolation plots processed": total,
            "Total surrounding plots processed": len(self.sur_gdf),
            "Total comparisons made": len(self.results),
            'Number of "Other Crop" cases': other_crop,
            "Number outside specified distance": outside_distance,
            "Number with no flowering overlap": no_overlap,
            "Number of synchronized pairs": synced,
            "Maximum overlap days": max(overlap_days_list) if overlap_days_list else 0,
            "Minimum overlap days": min(overlap_days_list) if overlap_days_list else 0,
            "Average overlap days": (
                round(sum(overlap_days_list) / len(overlap_days_list), 2)
                if overlap_days_list else 0
            ),
        }

        self._log("-" * 50)
        self._log("Analysis finished.")
        self._progress(100, "Finished")

        return self.results, self.stats

    # ------------------------------------------------------------
    @staticmethod
    def _row(iso_id, iso_crop, iso_start, iso_end,
             sur_id, sur_crop, sur_start, sur_end,
             distance, crop_match, flower_overlap,
             overlap_start, overlap_end, overlap_days, remarks):
        return {
            "Isolation_ID": iso_id,
            "Isolation_Crop": iso_crop,
            "Isolation_Start": format_date(iso_start),
            "Isolation_End": format_date(iso_end),
            "Surrounding_ID": sur_id,
            "Surrounding_Crop": sur_crop,
            "Surrounding_Start": format_date(sur_start),
            "Surrounding_End": format_date(sur_end),
            "Distance_m": round(distance, 2) if distance is not None else "",
            "Crop_Match": crop_match,
            "Flower_Overlap": flower_overlap,
            "Overlap_Start": format_date(overlap_start),
            "Overlap_End": format_date(overlap_end),
            "Overlap_Days": overlap_days if overlap_days is not None else "",
            "Remarks": remarks,
        }
