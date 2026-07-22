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

Step 5 – Overlap Percentage & Risk Classification
  Flowering Overlap (%) = (Overlap Days / Hybrid Flowering Days) × 100

  Overlap-based risk (fixed):
    0 days   → Safe
    1–2 days → Low
    3–5 days → Moderate
    >5 days  → High

  Combined risk uses user-defined distance bands:
    The analysis distance limit is divided equally into N bands.
    Risk labels are assigned from nearest→farthest:
      Very High → High → Moderate → Low → Safe  (clipped to available labels)
    The overlap-based risk is then combined: final risk = max(distance_band_risk, overlap_risk)
==========================================================
"""

from utils import parse_date, safe_str, crops_match, format_date
from spatial import build_spatial_index, query_nearby, compute_distance


# ── Risk label ordering (low index = least severe) ────────────────────────────
_RISK_ORDER = ["Safe", "Low", "Moderate", "High", "Very High"]


def _risk_index(label):
    try:
        return _RISK_ORDER.index(label)
    except ValueError:
        return 0


def max_risk(a, b):
    """Return the more severe of two risk labels."""
    return _RISK_ORDER[max(_risk_index(a), _risk_index(b))]


# ── Overlap-day risk (fixed thresholds) ───────────────────────────────────────

def classify_overlap_risk(overlap_days):
    """
    0 days   → Safe
    1–2 days → Low
    3–5 days → Moderate
    >5 days  → High
    """
    if overlap_days is None or overlap_days == 0:
        return "Safe"
    if overlap_days <= 2:
        return "Low"
    if overlap_days <= 5:
        return "Moderate"
    return "High"


# ── Overlap percentage ────────────────────────────────────────────────────────

def compute_overlap_percentage(overlap_days, hybrid_flowering_days):
    """Flowering Overlap (%) = (Overlap Days / Hybrid Flowering Days) × 100"""
    if hybrid_flowering_days and hybrid_flowering_days > 0 and overlap_days:
        return round((overlap_days / hybrid_flowering_days) * 100, 1)
    return None


# ── Dynamic distance-band risk ────────────────────────────────────────────────

def build_distance_bands(distance_limit, num_divisions):
    """
    Split distance_limit into num_divisions equal bands.
    Nearest band → Very High, farthest → least severe label.

    Returns a list of (upper_bound, risk_label) tuples sorted ascending.
    Example: limit=400, divisions=4 →
      [(100, "Very High"), (200, "High"), (300, "Moderate"), (400, "Low")]
    """
    band_size = distance_limit / num_divisions
    # Labels assigned from farthest to nearest so nearest = highest risk
    # We have 5 labels; clip to num_divisions
    labels_far_to_near = list(reversed(_RISK_ORDER))  # Very High … Safe
    bands = []
    for i in range(num_divisions):
        upper = round((i + 1) * band_size, 4)
        label_idx = max(len(_RISK_ORDER) - 1 - i, 0)
        risk_label = _RISK_ORDER[-(i + 1)]        # nearest band = highest label
        bands.append((upper, risk_label))
    bands.sort(key=lambda x: x[0])
    return bands


def classify_distance_band_risk(distance_m, bands):
    """
    Given the pre-built bands list and a distance, return the band's risk label.
    Plots beyond the last band boundary return 'Safe'.
    """
    if distance_m is None:
        return "Safe"
    for upper, label in bands:
        if distance_m <= upper:
            return label
    return "Safe"


def classify_combined_risk(distance_m, overlap_risk, bands):
    """
    Final risk = max(distance_band_risk, overlap_risk).
    If overlap is Safe, distance band alone sets the risk.
    """
    if overlap_risk == "Safe":
        return "Safe"
    dist_risk = classify_distance_band_risk(distance_m, bands)
    return max_risk(dist_risk, overlap_risk)


# ── Main analysis class ───────────────────────────────────────────────────────

class FloweringSynchronisation:
    """
    Runs the isolation-vs-surrounding flowering synchronisation analysis.

    Parameters
    ----------
    iso_gdf, sur_gdf : GeoDataFrame
    iso_fields, sur_fields : dict  (keys: id, crop, start, end)
    crop_compare : str
    distance_limit : float  – max proximity distance in metres
    distance_method : str   – 'centroid' or 'edge'
    risk_divisions : int    – how many equal bands to split distance_limit into
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
        risk_divisions=3,
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
        self.risk_divisions = max(2, int(risk_divisions))
        self.progress_callback = progress_callback or (lambda pct, msg: None)
        self.log_callback = log_callback or (lambda msg: None)

        # Build distance bands once
        self.distance_bands = build_distance_bands(self.distance_limit, self.risk_divisions)

        self.results = []
        self.stats = {}

    # ------------------------------------------------------------------
    def _progress(self, pct, msg=""):
        self.progress_callback(pct, msg)

    def _log(self, msg):
        self.log_callback(msg)

    # ------------------------------------------------------------------
    def run(self):
        self._progress(5, "Preparing data...")
        self._log("-" * 50)
        self._log(f"Isolation plots loaded : {len(self.iso_gdf)}")
        self._log(f"Surrounding plots loaded : {len(self.sur_gdf)}")
        self._log(f"Distance limit : {self.distance_limit} m | Divisions : {self.risk_divisions}")
        band_desc = " | ".join(f"≤{ub:.0f}m={lbl}" for ub, lbl in self.distance_bands)
        self._log(f"Distance bands : {band_desc}")

        iso_id_f    = self.iso_fields["id"]
        iso_crop_f  = self.iso_fields["crop"]
        iso_start_f = self.iso_fields["start"]
        iso_end_f   = self.iso_fields["end"]

        sur_id_f    = self.sur_fields["id"]
        sur_crop_f  = self.sur_fields["crop"]
        sur_start_f = self.sur_fields["start"]
        sur_end_f   = self.sur_fields["end"]

        self._progress(20, "Building spatial index...")
        sindex = build_spatial_index(self.sur_gdf)
        self._log("Spatial index created.")

        total = len(self.iso_gdf)
        other_crop = outside_distance = no_overlap = synced = 0
        overlap_days_list = []

        for pos, iso_row in self.iso_gdf.iterrows():
            pct = 20 + int(70 * (pos + 1) / max(total, 1))
            self._progress(pct, f"Checking Isolation Plot {pos + 1}/{total}...")

            iso_id    = safe_str(iso_row.get(iso_id_f, pos)) if iso_id_f else str(pos)
            iso_crop  = safe_str(iso_row.get(iso_crop_f, ""))
            iso_start = parse_date(iso_row.get(iso_start_f))
            iso_end   = parse_date(iso_row.get(iso_end_f))
            iso_geom  = iso_row.geometry

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

            # Hybrid flowering duration (for overlap %)
            hybrid_days = None
            if iso_start and iso_end:
                hybrid_days = (iso_end - iso_start).days + 1

            for spos in candidate_positions:
                sur_row  = self.sur_gdf.iloc[spos]
                sur_geom = sur_row.geometry
                if sur_geom is None or sur_geom.is_empty:
                    continue

                sur_id    = safe_str(sur_row.get(sur_id_f, spos)) if sur_id_f else str(spos)
                sur_crop  = safe_str(sur_row.get(sur_crop_f, ""))
                sur_start = parse_date(sur_row.get(sur_start_f))
                sur_end   = parse_date(sur_row.get(sur_end_f))

                # ── Crop check ──────────────────────────────────────────────
                target_crop = self.crop_compare if self.crop_compare else iso_crop
                crop_ok = crops_match(iso_crop, target_crop) and crops_match(sur_crop, target_crop)
                if not self.crop_compare:
                    crop_ok = crops_match(iso_crop, sur_crop)

                if not crop_ok:
                    other_crop += 1
                    self.results.append(self._row(
                        iso_id, iso_crop, iso_start, iso_end,
                        sur_id, sur_crop, sur_start, sur_end,
                        None, "No", "No", None, None, None,
                        None, None, None, "Other Crop"
                    ))
                    continue

                # ── Distance ────────────────────────────────────────────────
                distance = compute_distance(iso_geom, sur_geom, self.distance_method)

                if distance > self.distance_limit:
                    outside_distance += 1
                    self.results.append(self._row(
                        iso_id, iso_crop, iso_start, iso_end,
                        sur_id, sur_crop, sur_start, sur_end,
                        distance, "Yes", "No", None, None, None,
                        None, None, None, "Outside Distance"
                    ))
                    continue

                self._log(f"    Plot {sur_id} | Crop: {sur_crop} | Distance: {distance:.1f} m")

                # ── Flowering overlap ────────────────────────────────────────
                overlap_start = overlap_end = None
                overlap_days = 0

                if iso_start and iso_end and sur_start and sur_end:
                    overlap_start = max(iso_start, sur_start)
                    overlap_end   = min(iso_end,   sur_end)
                    delta = (overlap_end - overlap_start).days + 1
                    overlap_days = delta if delta > 0 else 0

                # ── Step 5: Overlap % and risk ───────────────────────────────
                overlap_pct   = compute_overlap_percentage(overlap_days, hybrid_days)
                overlap_risk  = classify_overlap_risk(overlap_days)
                combined_risk = classify_combined_risk(distance, overlap_risk, self.distance_bands)

                if overlap_days <= 0:
                    no_overlap += 1
                    remarks = "No Flower Synchronisation"
                    self._log("    Flower Overlap: 0 days -> No Flower Synchronisation")
                else:
                    synced += 1
                    overlap_days_list.append(overlap_days)
                    remarks = "Crop Flowering Sync"
                    self._log(
                        f"    Flower Overlap: {overlap_days} days | "
                        f"Overlap%: {overlap_pct} | "
                        f"Overlap Risk: {overlap_risk} | "
                        f"Final Risk: {combined_risk}"
                    )

                self.results.append(self._row(
                    iso_id, iso_crop, iso_start, iso_end,
                    sur_id, sur_crop, sur_start, sur_end,
                    distance, "Yes", "Yes" if overlap_days > 0 else "No",
                    overlap_start, overlap_end, overlap_days,
                    overlap_pct, overlap_risk, combined_risk,
                    remarks
                ))

        self._progress(95, "Finalising results...")

        self.stats = {
            "Total isolation plots processed":   total,
            "Total surrounding plots processed": len(self.sur_gdf),
            "Total comparisons made":            len(self.results),
            'Number of "Other Crop" cases':      other_crop,
            "Number outside specified distance": outside_distance,
            "Number with no flowering overlap":  no_overlap,
            "Number of synchronized pairs":      synced,
            "Maximum overlap days":  max(overlap_days_list) if overlap_days_list else 0,
            "Minimum overlap days":  min(overlap_days_list) if overlap_days_list else 0,
            "Average overlap days":  (
                round(sum(overlap_days_list) / len(overlap_days_list), 2)
                if overlap_days_list else 0
            ),
        }

        self._log("-" * 50)
        self._log("Analysis finished.")
        self._progress(100, "Finished")

        return self.results, self.stats

    # ------------------------------------------------------------------
    @staticmethod
    def _row(iso_id, iso_crop, iso_start, iso_end,
             sur_id, sur_crop, sur_start, sur_end,
             distance, crop_match, flower_overlap,
             overlap_start, overlap_end, overlap_days,
             overlap_pct, overlap_risk, combined_risk,
             remarks):
        return {
            "Isolation_ID":       iso_id,
            "Isolation_Crop":     iso_crop,
            "Isolation_Start":    format_date(iso_start),
            "Isolation_End":      format_date(iso_end),
            "Surrounding_ID":     sur_id,
            "Surrounding_Crop":   sur_crop,
            "Surrounding_Start":  format_date(sur_start),
            "Surrounding_End":    format_date(sur_end),
            "Distance_m":         round(distance, 2) if distance is not None else "",
            "Crop_Match":         crop_match,
            "Flower_Overlap":     flower_overlap,
            "Overlap_Start":      format_date(overlap_start),
            "Overlap_End":        format_date(overlap_end),
            "Overlap_Days":       overlap_days if overlap_days is not None else "",
            "Overlap_%":          overlap_pct if overlap_pct is not None else "",
            "Overlap_Risk":       overlap_risk if overlap_risk is not None else "",
            "Final_Risk":         combined_risk if combined_risk is not None else "",
            "Remarks":            remarks,
        }
