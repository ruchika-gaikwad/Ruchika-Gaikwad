# Project B: NYC 311 Data Quality Layer (Beginner Guide)

Welcome to **Project B**! This guide explains what this project does, how it works, and how each file connects, using simple everyday language.

---

## 1. What is Project B all about?

Imagine a city like New York where citizens report complaints (potholes, loud noise, dirty streets) using the **NYC 311 app**. Every day, thousands of rows of data flow into the city's database.

In real life, data often gets messed up:
- A sensor swaps **Latitude** and **Longitude**.
- Someone types `"Closed"` on a ticket, but the note says *"We haven't fixed it yet!"*
- A citizen accidentally posts their **phone number or email** in a public comment.
- A bug causes a column like `Incident Zip` to suddenly become 100% empty (**Null spike**).

### The Big Question:
Should we use **regular code (Rules)**, **Statistics (Math)**, or an **AI (LLM like Gemini)** to catch these bugs?
- If we use AI for every row, it costs thousands of dollars and takes hours.
- If we use simple rules only, we miss subtle text problems like contradictions and leaked names.
- **The Solution:** We build a **3-Tier Cascading Filter** that runs the cheapest checks first and only calls the AI when necessary!

---

## 2. The 12 Data Problems We Test (Simple Summary)

| Code | Problem Name | What it means in plain English | Best Detector |
| :---: | :--- | :--- | :---: |
| **a** | Renamed or Dropped Column | A column is missing or spelled wrong (e.g., `Agency` became `Dept`). | **Rules** |
| **b** | Column Type Change | A number arrived as a string or letters (e.g., `"abc"` in `Latitude`). | **Rules** |
| **c** | Date Format Switch | A date switched from `YYYY-MM-DD` to `DD/MM/YYYY`. | **Rules** |
| **d** | Lat / Lon Swapped | Inverted coordinates: Latitude is -74 and Longitude is 40. | **Rules** |
| **e** | Exact Duplicates | The exact same row was inserted twice. | **Rules** |
| **f** | Near-Duplicates | Someone submitted the same complaint with slightly different wording. | **Statistics** |
| **g** | Null Spike | An agency's records suddenly have 80% missing ZIP codes. | **Statistics** |
| **h** | Closed Date < Created Date | A ticket was closed *before* it was even created! | **Rules** |
| **i** | ZIP vs Borough Mismatch | A Manhattan ZIP code (`10001`) paired with `"Brooklyn"`. | **Rules** |
| **j** | Complaint vs Descriptor | Nonsense pairs, like `Complaint: Noise` paired with `Descriptor: Pothole`. | **Rules** |
| **k** | Status Contradiction in Text | Status says `"Closed"`, but description says *"Still working on it"*. | **AI (LLM)** |
| **l** | PII Leakage | A citizen's phone number or email was leaked in public text. | **Hybrid (Regex + AI)** |

---

## 3. How the Files Work Together

Here is the map of every file in `project_b/`:

```text
project_b/
├── data_loader.py                 <-- Generates 1,000 clean baseline NYC 311 records
├── injector.py                    <-- The "Troublemaker": injects the 12 problems on purpose
├── profiler.py                    <-- Audits raw data to see real-world quality issues
├── detectors/
│   ├── rules_detector.py          <-- Tier 1: Fast rules (checks schema, dates, coordinates)
│   ├── statistical_detector.py    <-- Tier 2: Statistics (calculates Z-scores & text similarity)
│   └── llm_detector.py            <-- Tier 3: Gemini AI (reads text for status contradictions & PII)
├── hybrid_pipeline.py             <-- The "Manager": runs Tier 1 -> Tier 2 -> Tier 3 cascade
└── test_project_b.py              <-- The "Scorecard": tests everything and prints the results table
```

---

## 4. The 3-Tier Airport Security Analogy

Think of our hybrid pipeline like **airport security**:

1. **Tier 1 (Metal Detector - Rules):**
   - Everyone walks through it.
   - Extremely fast (2.5 million rows per second).
   - Costs **$0.00**.
   - Catches 8 out of the 12 problem types immediately!

2. **Tier 2 (X-Ray Scanner - Statistics):**
   - Looks at groups/batches of rows.
   - Compares current numbers against historical averages using **Z-scores** (for null spikes) and **Jaccard math** (for near-duplicate text).
   - Still costs **$0.00** and runs in milliseconds.

3. **Tier 3 (Manual Physical Inspection - AI / LLM):**
   - Only called for the **1% suspicious rows** that pass through Tiers 1 and 2.
   - Uses Gemini AI to understand the meaning (semantics) of English text.
   - Because it only inspects 1% of rows, **costs drop by 99.1%**!

---

## 5. How to Run It Yourself

Run the full benchmark from your terminal:
```powershell
python project_b/test_project_b.py
```
Or via the unified CLI:
```powershell
python main.py --project-b
```
