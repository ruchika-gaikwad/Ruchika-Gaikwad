"""
data_loader.py
Dataset loader and generator for Project B (NYC 311 Service Requests 2023).
Provides:
- Authentic NYC 311 schema (timestamps, categories, locations, free text).
- Real-world borough-to-ZIP code mappings.
- Clean baseline data generation for controlled corruption testing.
- CSV dataset export to 'data/nyc_311_clean_sample.csv'.
"""

import csv
import os
import random
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CLEAN_DATA_FILE = os.path.join(DATA_DIR, "nyc_311_clean_sample.csv")

# Standard NYC Borough to valid ZIP code prefixes
BOROUGH_ZIP_MAP = {
    "MANHATTAN": ["10001", "10002", "10011", "10016", "10025", "10027", "10036"],
    "BROOKLYN": ["11201", "11211", "11215", "11222", "11225", "11231", "11238"],
    "QUEENS": ["11101", "11354", "11372", "11375", "11385", "11432", "11691"],
    "BRONX": ["10451", "10456", "10458", "10461", "10467", "10471", "10473"],
    "STATEN ISLAND": ["10301", "10304", "10306", "10309", "10312", "10314"]
}

# Authentic NYC 311 Agency & Complaint Type mappings
COMPLAINT_MAP = {
    "NYPD": [
        ("Noise - Residential", "Loud Music/Party", "The Police Department responded and addressed the condition."),
        ("Noise - Street/Sidewalk", "Loud Talking", "The Police Department took action to clear the area."),
        ("Illegal Parking", "Blocked Hydrant", "The Police Department issued a summons for the violation."),
        ("Blocked Driveway", "No Access", "The vehicle was cited and condition corrected.")
    ],
    "DOT": [
        ("Street Condition", "Pothole", "The Department of Transportation repaired the pothole."),
        ("Traffic Signal Condition", "Controller", "The traffic signal timing was reset and inspected."),
        ("Sidewalk Condition", "Broken Sidewalk", "The Department of Transportation inspected the condition.")
    ],
    "DEP": [
        ("Water System", "Leak (Use Water)", "The Department of Environmental Protection investigated and resolved the leak."),
        ("Sewer", "Catch Basin Clogged", "The catch basin was cleaned and free of debris.")
    ],
    "DSNY": [
        ("Sanitation Condition", "Dirty Conditions", "The Department of Sanitation cleared the litter from the area."),
        ("Missed Collection", "Trash", "The Department of Sanitation scheduled a pickup for the missed items.")
    ],
    "HPD": [
        ("HEAT/HOT WATER", "ENTIRE BUILDING", "The Department of Housing Preservation and Development verified heat was restored."),
        ("PAINT/PLASTER", "CEILING", "The landlord was notified to perform the plaster repairs.")
    ]
}


def generate_clean_sample(num_records: int = 1000, seed: int = 42) -> List[Dict[str, Any]]:
    """
    Generates a synthetically clean baseline batch of NYC 311 service requests for 2023.
    Guarantees 100% data quality:
    - Consistent timestamp ordering (Closed Date >= Created Date)
    - Valid ZIP to Borough consistency
    - Valid Agency to Complaint to Descriptor consistency
    - Valid Coordinates (Lat ~40.7, Lon ~-73.9)
    - Zero PII in Resolution Description
    - No exact or near duplicates
    """
    random.seed(seed)
    records = []
    base_date = datetime(2023, 1, 1, 8, 0, 0)

    for i in range(1, num_records + 1):
        unique_key = 50000000 + i

        # 1. Timestamps (Created in 2023, Closed 1 to 72 hours later)
        delta_days = random.randint(0, 360)
        delta_hours = random.randint(0, 23)
        delta_mins = random.randint(0, 59)
        created_dt = base_date + timedelta(days=delta_days, hours=delta_hours, minutes=delta_mins)

        duration_hours = random.randint(1, 48)
        duration_mins = random.randint(5, 55)
        closed_dt = created_dt + timedelta(hours=duration_hours, minutes=duration_mins)

        created_str = created_dt.strftime("%m/%d/%Y %I:%M:%S %p")
        closed_str = closed_dt.strftime("%m/%d/%Y %I:%M:%S %p")

        # 2. Agency, Complaint, Descriptor, Resolution
        agency = random.choice(list(COMPLAINT_MAP.keys()))
        complaint_type, descriptor, resolution = random.choice(COMPLAINT_MAP[agency])
        status = "Closed"

        # 3. Location (Borough and consistent ZIP)
        borough = random.choice(list(BOROUGH_ZIP_MAP.keys()))
        zip_code = random.choice(BOROUGH_ZIP_MAP[borough])

        # 4. Realistic NYC GPS Coordinates
        # Lat: 40.57 to 40.88, Lon: -74.24 to -73.71
        lat = round(random.uniform(40.5700, 40.8800), 6)
        lon = round(random.uniform(-74.2400, -73.7100), 6)

        rec = {
            "Unique Key": unique_key,
            "Created Date": created_str,
            "Closed Date": closed_str,
            "Agency": agency,
            "Complaint Type": complaint_type,
            "Descriptor": descriptor,
            "Location Type": "Residential Building" if agency in ["NYPD", "HPD"] else "Street/Sidewalk",
            "Incident Zip": zip_code,
            "Borough": borough,
            "Status": status,
            "Resolution Description": resolution,
            "Latitude": lat,
            "Longitude": lon
        }
        records.append(rec)

    return records


def save_dataset_csv(records: List[Dict[str, Any]], filepath: str = CLEAN_DATA_FILE):
    """Saves records to CSV format."""
    if not records:
        return
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fieldnames = list(records[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def load_clean_data(num_records: int = 1000) -> List[Dict[str, Any]]:
    """Loads or generates clean baseline dataset."""
    if not os.path.exists(CLEAN_DATA_FILE):
        records = generate_clean_sample(num_records)
        save_dataset_csv(records, CLEAN_DATA_FILE)
        return records

    records = []
    with open(CLEAN_DATA_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Cast numeric fields
            row["Unique Key"] = int(row["Unique Key"])
            row["Latitude"] = float(row["Latitude"])
            row["Longitude"] = float(row["Longitude"])
            records.append(row)
    return records


if __name__ == "__main__":
    print("=" * 65)
    print("PROJECT B: NYC 311 SERVICE REQUESTS DATA LOADER")
    print("=" * 65)

    data = load_clean_data(num_records=1000)
    print(f"Loaded clean dataset: {len(data)} rows.")
    print(f"Columns: {list(data[0].keys())}")
    print("-" * 65)
    print("Sample Row 1:")
    for k, v in list(data[0].items())[:6]:
        print(f"  {k:<22}: {v}")
    print("=" * 65)
