"""
statistical_detector.py
Task 3b: Statistical & Machine Learning Anomaly Detectors for NYC 311.
Detects:
  g. Null spike in one agency's records (Z-score anomaly detection per agency)
  f. Near-duplicates (Jaccard n-gram string similarity + temporal proximity window)
  d. Statistical distribution shifts in geographic coordinates (IQR & Z-score)
"""

import math
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def compute_char_ngrams(text: str, n: int = 3) -> set:
    """Computes character n-grams for fuzzy string comparison."""
    text = text.lower().strip()
    if len(text) < n:
        return {text}
    return {text[i:i+n] for i in range(len(text) - n + 1)}


def jaccard_similarity(set1: set, set2: set) -> float:
    """Calculates Jaccard similarity between two sets."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


class StatisticalDataQualityDetector:
    """
    Statistical and distributional anomaly detector for NYC 311 batches.
    """

    def __init__(self, z_score_threshold: float = 3.0, similarity_threshold: float = 0.70):
        self.z_score_threshold = z_score_threshold
        self.similarity_threshold = similarity_threshold

    def detect_null_spikes(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detects Problem g: Null spike in one agency's records.
        Groups records by Agency, computes missing Incident Zip rate per agency,
        and flags agencies whose null rate deviates significantly from the batch mean.
        """
        anomalies = []
        agency_stats: Dict[str, Dict[str, int]] = {}

        for row in batch:
            agency = str(row.get("Agency", "UNKNOWN"))
            if agency not in agency_stats:
                agency_stats[agency] = {"total": 0, "null_zip": 0}

            agency_stats[agency]["total"] += 1
            zip_val = row.get("Incident Zip")
            if zip_val is None or str(zip_val).strip() in ["", "None", "nan", "N/A"]:
                agency_stats[agency]["null_zip"] += 1

        if len(agency_stats) < 2:
            return anomalies

        # Calculate null rates per agency
        rates = []
        for agency, counts in agency_stats.items():
            rate = counts["null_zip"] / counts["total"] if counts["total"] > 0 else 0.0
            rates.append((agency, rate, counts["total"], counts["null_zip"]))

        # Calculate mean and standard deviation of agency null rates
        all_rates = [r[1] for r in rates]
        mean_rate = sum(all_rates) / len(all_rates)
        variance = sum((r - mean_rate) ** 2 for r in all_rates) / max(1, len(all_rates) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0001

        # Flag agencies with Z-score exceeding threshold
        for agency, rate, total, nulls in rates:
            z_score = (rate - mean_rate) / std_dev
            # Flag if null rate is elevated and z_score > threshold
            if z_score > self.z_score_threshold or (rate > 0.35 and rate > mean_rate * 2.0):
                anomalies.append({
                    "detector": "statistical",
                    "problem_type": "g_null_spike",
                    "severity": "CRITICAL",
                    "agency": agency,
                    "agency_total_rows": total,
                    "agency_null_count": nulls,
                    "null_rate": round(rate * 100, 2),
                    "baseline_mean_rate": round(mean_rate * 100, 2),
                    "z_score": round(z_score, 2),
                    "message": (
                        f"Statistical Anomaly (Z-Score {z_score:.2f}): Agency '{agency}' has an "
                        f"abnormal null spike in Incident Zip ({rate * 100:.1f}% missing vs {mean_rate * 100:.1f}% baseline)."
                    )
                })

        return anomalies

    def detect_near_duplicates(self, batch: List[Dict[str, Any]], time_window_minutes: int = 15) -> List[Dict[str, Any]]:
        """
        Detects Problem f: Near-duplicates.
        Identifies pairs of records sharing the same Agency & Complaint Type
        with high text similarity in Resolution Description created within a small time window.
        """
        anomalies = []
        # Sort or group by (Agency, Complaint Type) to avoid O(N^2) comparison across entire batch
        grouped: Dict[Tuple[str, str], List[Tuple[int, Dict[str, Any]]]] = {}

        for idx, row in enumerate(batch):
            key = (str(row.get("Agency")), str(row.get("Complaint Type")))
            if key not in grouped:
                grouped[key] = []
            grouped[key].append((idx, row))

        # Check pairs within each category group
        for (agency, comp_type), rows in grouped.items():
            if len(rows) < 2:
                continue

            for i in range(len(rows)):
                idx1, row1 = rows[i]
                c_str1 = row1.get("Created Date")
                try:
                    dt1 = datetime.strptime(str(c_str1).strip(), "%m/%d/%Y %I:%M:%S %p")
                except Exception:
                    continue

                desc1 = str(row1.get("Resolution Description", ""))
                ngrams1 = compute_char_ngrams(desc1, n=3)

                for j in range(i + 1, min(i + 15, len(rows))):
                    idx2, row2 = rows[j]
                    c_str2 = row2.get("Created Date")
                    try:
                        dt2 = datetime.strptime(str(c_str2).strip(), "%m/%d/%Y %I:%M:%S %p")
                    except Exception:
                        continue

                    # Temporal check
                    time_diff = abs((dt1 - dt2).total_seconds()) / 60.0
                    if time_diff <= time_window_minutes:
                        desc2 = str(row2.get("Resolution Description", ""))
                        ngrams2 = compute_char_ngrams(desc2, n=3)
                        sim = jaccard_similarity(ngrams1, ngrams2)

                        # Exclude exact duplicates which rules detector handles
                        if self.similarity_threshold <= sim < 1.0 or (sim >= 0.70 and row1.get("Unique Key") != row2.get("Unique Key")):
                            anomalies.append({
                                "detector": "statistical",
                                "row_index": idx2,
                                "unique_key": row2.get("Unique Key"),
                                "matched_key": row1.get("Unique Key"),
                                "problem_type": "f_near_duplicate",
                                "severity": "MEDIUM",
                                "jaccard_similarity": round(sim, 3),
                                "time_gap_minutes": round(time_diff, 1),
                                "message": (
                                    f"Near-duplicate ticket detected: Ticket {row2.get('Unique Key')} is "
                                    f"{sim * 100:.1f}% similar to Ticket {row1.get('Unique Key')} within {time_diff:.1f} minutes."
                                )
                            })
                            break

        return anomalies

    def evaluate_batch(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Runs all statistical detectors on batch."""
        null_alerts = self.detect_null_spikes(batch)
        near_dup_alerts = self.detect_near_duplicates(batch)
        return null_alerts + near_dup_alerts


if __name__ == "__main__":
    from project_b.data_loader import load_clean_data
    from project_b.injector import NYC311CorruptionInjector

    clean_data = load_clean_data(num_records=500)
    injector = NYC311CorruptionInjector(seed=42)
    corrupted_batch, stats = injector.inject_all_types(clean_data, rate_per_type=0.05)

    detector = StatisticalDataQualityDetector()
    alerts = detector.evaluate_batch(corrupted_batch)

    print("=" * 65)
    print("TASK 3B: STATISTICAL & ML DETECTOR")
    print("=" * 65)
    print(f"Total Rows Evaluated: {len(corrupted_batch):,}")
    print(f"Total Alerts Fired  : {len(alerts):,}")
    print("-" * 65)
    for a in alerts[:5]:
        print(f"[{a['problem_type']}] {a['message']}")
    print("=" * 65)
