"""
rules_detector.py
Task 3a: Declarative Rules & Schema Detector for NYC 311 Service Requests.
Detects:
  a. Renamed or dropped columns (schema validation)
  b. Column type anomalies (numeric columns holding strings)
  c. Date format anomalies (inconsistent timestamp strings)
  d. Swapped coordinates (spatial bound checks: NYC Lat [40.5, 40.9], Lon [-74.3, -73.7])
  e. Exact duplicate rows
  h. Inverted timestamps (Closed Date < Created Date)
  i. ZIP code inconsistent with declared Borough
  j. Complaint Type inconsistent with Descriptor
  l. PII leakage (regex-based telephone & email patterns)
"""

import os
import re
import sys
from datetime import datetime
from typing import List, Dict, Any, Set, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from project_b.data_loader import BOROUGH_ZIP_MAP, COMPLAINT_MAP

EXPECTED_SCHEMA = [
    "Unique Key", "Created Date", "Closed Date", "Agency",
    "Complaint Type", "Descriptor", "Location Type", "Incident Zip",
    "Borough", "Status", "Resolution Description", "Latitude", "Longitude"
]

PHONE_REGEX = re.compile(r"\b(?:\+?1[-.]?)?\(?[2-9]\d{2}\)?[-.]?\d{3}[-.]?\d{4}\b")
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


class RulesDataQualityDetector:
    """
    High-throughput, deterministic rule-based detector for NYC 311 records.
    """

    def __init__(self):
        self.valid_pairs = set()
        for agency, pairs in COMPLAINT_MAP.items():
            for c_type, desc, _ in pairs:
                self.valid_pairs.add((c_type.lower(), desc.lower()))

    def check_schema(self, columns: List[str]) -> List[Dict[str, Any]]:
        """Detects renamed, dropped, or missing columns (Problem a)."""
        anomalies = []
        col_set = set(columns)
        for expected in EXPECTED_SCHEMA:
            if expected not in col_set:
                anomalies.append({
                    "detector": "rules",
                    "problem_type": "a_schema_altered",
                    "severity": "CRITICAL",
                    "column": expected,
                    "message": f"Schema violation: Mandatory column '{expected}' is missing or was renamed."
                })
        return anomalies

    def evaluate_batch(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Runs row-level declarative rule checks across a batch.
        Returns list of detected anomalies.
        """
        anomalies = []
        seen_keys: Set[Any] = set()
        seen_content_hashes: Set[int] = set()

        for idx, row in enumerate(batch):
            row_id = row.get("Unique Key", f"row_{idx}")

            # 1. Exact Duplicate Check (Problem e)
            content_tuple = (
                str(row.get("Created Date")),
                str(row.get("Agency")),
                str(row.get("Complaint Type")),
                str(row.get("Descriptor")),
                str(row.get("Incident Zip")),
                str(row.get("Latitude")),
                str(row.get("Longitude"))
            )
            content_hash = hash(content_tuple)
            if content_hash in seen_content_hashes or row_id in seen_keys:
                anomalies.append({
                    "detector": "rules",
                    "row_index": idx,
                    "unique_key": row_id,
                    "problem_type": "e_exact_duplicate",
                    "severity": "MEDIUM",
                    "message": f"Exact duplicate record detected for Unique Key {row_id}."
                })
            else:
                seen_keys.add(row_id)
                seen_content_hashes.add(content_hash)

            # 2. Column Type Check (Problem b: Latitude/Longitude/Key not numeric)
            lat = row.get("Latitude")
            lon = row.get("Longitude")
            is_lat_numeric = True
            try:
                lat_float = float(lat) if lat is not None else None
            except (ValueError, TypeError):
                is_lat_numeric = False
                anomalies.append({
                    "detector": "rules",
                    "row_index": idx,
                    "unique_key": row_id,
                    "problem_type": "b_type_change",
                    "severity": "HIGH",
                    "column": "Latitude",
                    "message": f"Type violation: Latitude contains non-numeric string value '{lat}'."
                })

            try:
                lon_float = float(lon) if lon is not None else None
            except (ValueError, TypeError):
                is_lat_numeric = False
                anomalies.append({
                    "detector": "rules",
                    "row_index": idx,
                    "unique_key": row_id,
                    "problem_type": "b_type_change",
                    "severity": "HIGH",
                    "column": "Longitude",
                    "message": f"Type violation: Longitude contains non-numeric string value '{lon}'."
                })

            # 3. Coordinate Swap Check (Problem d: NYC Lat ~40.7, Lon ~-73.9)
            if is_lat_numeric and lat_float is not None and lon_float is not None:
                # If latitude is negative (around -74) and longitude is positive (around 40)
                if lat_float < 0 and lon_float > 0:
                    anomalies.append({
                        "detector": "rules",
                        "row_index": idx,
                        "unique_key": row_id,
                        "problem_type": "d_lat_lon_swap",
                        "severity": "HIGH",
                        "message": f"Coordinates inverted: Latitude ({lat_float}) and Longitude ({lon_float}) are swapped."
                    })
                elif not (40.40 <= lat_float <= 41.10) or not (-74.40 <= lon_float <= -73.60):
                    # Out of NYC geographic bounding box
                    anomalies.append({
                        "detector": "rules",
                        "row_index": idx,
                        "unique_key": row_id,
                        "problem_type": "d_lat_lon_swap",
                        "severity": "MEDIUM",
                        "message": f"Coordinates ({lat_float}, {lon_float}) fall outside NYC geographic boundary."
                    })

            # 4. Date Format & Inversion Checks (Problems c & h)
            c_str = row.get("Created Date")
            cl_str = row.get("Closed Date")
            c_dt, cl_dt = None, None

            if c_str:
                try:
                    c_dt = datetime.strptime(str(c_str).strip(), "%m/%d/%Y %I:%M:%S %p")
                except ValueError:
                    anomalies.append({
                        "detector": "rules",
                        "row_index": idx,
                        "unique_key": row_id,
                        "problem_type": "c_date_format_switch",
                        "severity": "HIGH",
                        "message": f"Timestamp format violation in Created Date: '{c_str}' does not match MM/DD/YYYY HH:MM:SS AM/PM."
                    })

            if cl_str:
                try:
                    cl_dt = datetime.strptime(str(cl_str).strip(), "%m/%d/%Y %I:%M:%S %p")
                except ValueError:
                    anomalies.append({
                        "detector": "rules",
                        "row_index": idx,
                        "unique_key": row_id,
                        "problem_type": "c_date_format_switch",
                        "severity": "HIGH",
                        "message": f"Timestamp format violation in Closed Date: '{cl_str}'."
                    })

            if c_dt and cl_dt and cl_dt < c_dt:
                anomalies.append({
                    "detector": "rules",
                    "row_index": idx,
                    "unique_key": row_id,
                    "problem_type": "h_closed_before_created",
                    "severity": "CRITICAL",
                    "message": f"Temporal inversion: Closed Date ({cl_str}) is earlier than Created Date ({c_str})."
                })

            # 5. ZIP vs Borough Consistency (Problem i)
            borough = str(row.get("Borough", "")).strip().upper()
            zip_code = str(row.get("Incident Zip", "")).strip()
            if borough in BOROUGH_ZIP_MAP and zip_code and zip_code not in ["N/A", "None", ""]:
                valid_zips = BOROUGH_ZIP_MAP[borough]
                if zip_code not in valid_zips:
                    anomalies.append({
                        "detector": "rules",
                        "row_index": idx,
                        "unique_key": row_id,
                        "problem_type": "i_zip_borough_mismatch",
                        "severity": "HIGH",
                        "message": f"Geographic inconsistency: ZIP code '{zip_code}' is not a valid postal code for Borough '{borough}'."
                    })

            # 6. Complaint Type vs Descriptor Taxonomy (Problem j)
            c_type = str(row.get("Complaint Type", "")).strip().lower()
            desc = str(row.get("Descriptor", "")).strip().lower()
            if c_type and desc and (c_type, desc) not in self.valid_pairs:
                anomalies.append({
                    "detector": "rules",
                    "row_index": idx,
                    "unique_key": row_id,
                    "problem_type": "j_taxonomy_mismatch",
                    "severity": "MEDIUM",
                    "message": f"Taxonomy violation: Descriptor '{row.get('Descriptor')}' is invalid for Complaint Type '{row.get('Complaint Type')}'."
                })

            # 7. Regex PII Pattern Check (Problem l)
            res_desc = str(row.get("Resolution Description", ""))
            phones = PHONE_REGEX.findall(res_desc)
            emails = EMAIL_REGEX.findall(res_desc)
            if phones or emails:
                anomalies.append({
                    "detector": "rules",
                    "row_index": idx,
                    "unique_key": row_id,
                    "problem_type": "l_pii_leakage",
                    "severity": "CRITICAL",
                    "message": f"PII Privacy Breach: Free text contains telephone {phones} or email {emails}."
                })

        return anomalies


if __name__ == "__main__":
    from project_b.data_loader import load_clean_data
    from project_b.injector import NYC311CorruptionInjector

    clean_data = load_clean_data(num_records=500)
    injector = NYC311CorruptionInjector(seed=42)
    corrupted_batch, stats = injector.inject_all_types(clean_data, rate_per_type=0.05)

    detector = RulesDataQualityDetector()
    alerts = detector.evaluate_batch(corrupted_batch)

    print("=" * 65)
    print("TASK 3A: DECLARATIVE RULES DETECTOR")
    print("=" * 65)
    print(f"Total Rows Evaluated: {len(corrupted_batch):,}")
    print(f"Total Alerts Fired  : {len(alerts):,}")
    print("-" * 65)
    print("Alert breakdown by problem type:")
    alert_counts = {}
    for a in alerts:
        pt = a["problem_type"]
        alert_counts[pt] = alert_counts.get(pt, 0) + 1
    for pt, count in sorted(alert_counts.items()):
        print(f"  - {pt:<28}: {count} detected")
    print("=" * 65)
