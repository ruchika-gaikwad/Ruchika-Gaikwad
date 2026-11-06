"""
profiler.py
Task 1: Raw Data Profiler for NYC 311 Service Requests (2023).
Audits and profiles real-world data quality issues across 6 key dimensions:
1. Null and missing value rates per column.
2. Temporal logic flaws (Closed Date earlier than Created Date).
3. Geographic inconsistencies (ZIP code inconsistent with Borough).
4. Taxonomy mismatches (Complaint Type inconsistent with Descriptor).
5. Semantic status contradictions (Status 'Closed' contradicted by resolution text).
6. Personal Identifiable Information (PII) leakage in free-text fields.
"""

import csv
import os
import re
import sys
from datetime import datetime
from typing import List, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from project_b.data_loader import BOROUGH_ZIP_MAP, COMPLAINT_MAP


# PII regular expressions for US phone numbers and email addresses
PHONE_REGEX = re.compile(r"\b(?:\+?1[-.]?)?\(?[2-9]\d{2}\)?[-.]?\d{3}[-.]?\d{4}\b")
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


class NYC311DataProfiler:
    """
    Profiles raw batches of NYC 311 data to discover and quantify quality defects.
    """

    def __init__(self, records: List[Dict[str, Any]]):
        self.records = records
        self.total_rows = len(records)

    def profile_all(self) -> Dict[str, Any]:
        """
        Runs all quality audit profiles across the dataset.
        """
        null_profile = self._profile_nulls()
        temporal_profile = self._profile_temporal_logic()
        geo_profile = self._profile_geographic_consistency()
        taxonomy_profile = self._profile_taxonomy()
        status_profile = self._profile_status_contradictions()
        pii_profile = self._profile_pii_leaks()

        return {
            "total_rows_profiled": self.total_rows,
            "null_rates": null_profile,
            "temporal_anomalies": temporal_profile,
            "geographic_inconsistencies": geo_profile,
            "taxonomy_mismatches": taxonomy_profile,
            "status_contradictions": status_profile,
            "pii_leakage": pii_profile
        }

    def _profile_nulls(self) -> Dict[str, Any]:
        """Calculates missing and null value frequencies per column."""
        if not self.records:
            return {}

        columns = list(self.records[0].keys())
        null_counts = {col: 0 for col in columns}

        for row in self.records:
            for col in columns:
                val = row.get(col)
                if val is None or str(val).strip() in ["", "N/A", "nan", "None", "00000"]:
                    null_counts[col] += 1

        null_summary = {}
        for col, count in null_counts.items():
            pct = (count / self.total_rows) * 100 if self.total_rows > 0 else 0
            null_summary[col] = {
                "missing_count": count,
                "missing_percentage": round(pct, 2)
            }
        return null_summary

    def _profile_temporal_logic(self) -> Dict[str, Any]:
        """Detects instances where Closed Date is earlier than Created Date."""
        anomalies = []
        for idx, row in enumerate(self.records):
            created_str = row.get("Created Date")
            closed_str = row.get("Closed Date")
            if not created_str or not closed_str:
                continue

            try:
                c_dt = datetime.strptime(created_str.strip(), "%m/%d/%Y %I:%M:%S %p")
                cl_dt = datetime.strptime(closed_str.strip(), "%m/%d/%Y %I:%M:%S %p")
                if cl_dt < c_dt:
                    anomalies.append({
                        "row_index": idx,
                        "unique_key": row.get("Unique Key"),
                        "created_date": created_str,
                        "closed_date": closed_str,
                        "time_difference_hours": round((cl_dt - c_dt).total_seconds() / 3600, 2)
                    })
            except Exception:
                pass

        return {
            "count": len(anomalies),
            "percentage": round((len(anomalies) / max(1, self.total_rows)) * 100, 2),
            "examples": anomalies[:3]
        }

    def _profile_geographic_consistency(self) -> Dict[str, Any]:
        """Validates whether Incident Zip code matches the declared Borough."""
        inconsistencies = []
        for idx, row in enumerate(self.records):
            borough = str(row.get("Borough", "")).strip().upper()
            zip_code = str(row.get("Incident Zip", "")).strip()

            if borough in BOROUGH_ZIP_MAP:
                valid_zips = BOROUGH_ZIP_MAP[borough]
                if zip_code not in valid_zips and zip_code not in ["", "N/A"]:
                    inconsistencies.append({
                        "row_index": idx,
                        "unique_key": row.get("Unique Key"),
                        "borough": borough,
                        "incident_zip": zip_code,
                        "expected_borough_prefixes": [z[:3] for z in valid_zips[:2]]
                    })

        return {
            "count": len(inconsistencies),
            "percentage": round((len(inconsistencies) / max(1, self.total_rows)) * 100, 2),
            "examples": inconsistencies[:3]
        }

    def _profile_taxonomy(self) -> Dict[str, Any]:
        """Checks if Complaint Type and Descriptor match authentic agency taxonomy."""
        mismatches = []
        valid_pairs = set()
        for agency, pairs in COMPLAINT_MAP.items():
            for c_type, desc, _ in pairs:
                valid_pairs.add((c_type.lower(), desc.lower()))

        for idx, row in enumerate(self.records):
            c_type = str(row.get("Complaint Type", "")).strip().lower()
            desc = str(row.get("Descriptor", "")).strip().lower()
            if c_type and desc and (c_type, desc) not in valid_pairs:
                mismatches.append({
                    "row_index": idx,
                    "unique_key": row.get("Unique Key"),
                    "complaint_type": row.get("Complaint Type"),
                    "descriptor": row.get("Descriptor")
                })

        return {
            "count": len(mismatches),
            "percentage": round((len(mismatches) / max(1, self.total_rows)) * 100, 2),
            "examples": mismatches[:3]
        }

    def _profile_status_contradictions(self) -> Dict[str, Any]:
        """Identifies records where Status says 'Closed' but text contradicts it."""
        contradictions = []
        contradictory_keywords = ["pending", "in progress", "investigating", "open", "unresolved", "not yet", "scheduled"]

        for idx, row in enumerate(self.records):
            status = str(row.get("Status", "")).strip().lower()
            res_desc = str(row.get("Resolution Description", "")).strip().lower()

            if status == "closed":
                if any(kw in res_desc for kw in contradictory_keywords):
                    contradictions.append({
                        "row_index": idx,
                        "unique_key": row.get("Unique Key"),
                        "status": row.get("Status"),
                        "resolution_description": row.get("Resolution Description")
                    })

        return {
            "count": len(contradictions),
            "percentage": round((len(contradictions) / max(1, self.total_rows)) * 100, 2),
            "examples": contradictions[:3]
        }

    def _profile_pii_leaks(self) -> Dict[str, Any]:
        """Scans free-text fields for phone numbers and email addresses."""
        leaks = []
        for idx, row in enumerate(self.records):
            res_desc = str(row.get("Resolution Description", ""))
            phones = PHONE_REGEX.findall(res_desc)
            emails = EMAIL_REGEX.findall(res_desc)

            if phones or emails:
                leaks.append({
                    "row_index": idx,
                    "unique_key": row.get("Unique Key"),
                    "detected_phones": phones,
                    "detected_emails": emails,
                    "snippet": res_desc[:80] + "..." if len(res_desc) > 80 else res_desc
                })

        return {
            "count": len(leaks),
            "percentage": round((len(leaks) / max(1, self.total_rows)) * 100, 2),
            "examples": leaks[:3]
        }


def print_profile_report(profile: Dict[str, Any]):
    """Pretty prints the data quality profile report."""
    print("=" * 70)
    print("PROJECT B: RAW DATA QUALITY PROFILE (NYC 311 2023 DATASET)")
    print("=" * 70)
    print(f"Total Records Profiled: {profile['total_rows_profiled']:,}")
    print("-" * 70)

    print("1. MISSING / NULL RATES PER COLUMN:")
    for col, stat in list(profile["null_rates"].items())[:7]:
        print(f"   {col:<26}: {stat['missing_count']} missing ({stat['missing_percentage']}%)")

    print("\n2. QUALITY DEFECT SUMMARY:")
    defects = [
        ("Temporal Anomalies (Closed < Created)", profile["temporal_anomalies"]),
        ("ZIP vs Borough Inconsistencies", profile["geographic_inconsistencies"]),
        ("Complaint Type vs Descriptor Mismatch", profile["taxonomy_mismatches"]),
        ("Resolution Description Contradicting Status", profile["status_contradictions"]),
        ("Personal Data (PII) Leakage", profile["pii_leakage"])
    ]

    for name, data in defects:
        print(f"   - {name:<46}: {data['count']} defects ({data['percentage']}%)")
        if data["examples"]:
            print(f"     Example: {data['examples'][0]}")

    print("=" * 70)


if __name__ == "__main__":
    from project_b.data_loader import load_clean_data
    records = load_clean_data(num_records=1000)
    profiler = NYC311DataProfiler(records)
    report = profiler.profile_all()
    print_profile_report(report)
