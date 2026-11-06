# AI Usage Note: Fire AI Take-Home Assignment

## 1. Tools and Models Used
* **Primary LLM Integration:** Google Gemini API (`gemini-3.1-flash-lite`, ) via direct HTTPS REST endpoint.
* **Development Assistant:** Antigravity (Google DeepMind advanced agentic coding assistant) used for pair programming, test case generation, and architectural design.
* **Testing Frameworks:** Python standard `unittest` and `pytest` for executing the 210-case regression suite.

---

## 2. Where the AI Was Wrong and How It Was Caught

### Defect 1 (Project A): Section 87A Marginal Relief & Standard Deduction Hallucination
* **The Failure:** During live testing of Task 2b (`project_a/llm_calculator.py`), Gemini was tasked with calculating tax for an employee with Gross Salary ₹12,00,000 under the New Regime for FY 2024–25.
  * **Ground Truth (Indian Income Tax Department):**
    * Gross Salary: ₹12,00,000
    * Standard Deduction: ₹75,000 (hiked in Finance (No. 2) Act 2024)
    * Net Taxable Income: ₹11,25,000
    * Base Slab Tax: ₹68,750
    * 4% Cess: ₹2,750
    * **Total Tax Payable = ₹71,500**
  * **What the LLM Calculated:**
    * Gemini reported **₹85,800** in tax!
* **Root Cause of AI Error:**
  1. The LLM completely ignored the new ₹75,000 standard deduction and used the older ₹50,000 standard deduction (memorization interference).
  2. The LLM miscalculated the 15% slab between ₹10,00,000 and ₹12,00,000.
* **How It Was Caught:**
  * It was caught by our automated verification function `compare_calculations()` in `tax_utils.py` and the assertion suite in `test_rules.py`, which systematically audits candidate LLM calculations against deterministic ground truth.
* **Architectural Lesson:**
  * This confirmed our core thesis: **LLMs should never perform arithmetic calculations in financial engines**. All tax math must be delegated to deterministic rules, with LLMs used exclusively for natural language understanding.

---

### Defect 2 (Project B): Semantic False Alarms on Municipal SOP Terminology
* **The Failure:** During Task 3c testing of `project_b/detectors/llm_detector.py`, Gemini was asked to flag whether `Resolution Description` contradicted `Status: Closed`.
  * For the row:
    * `Status: Closed`
    * `Resolution Description: The Department of Sanitation scheduled a pickup for the missed items.`
  * The LLM flagged this as a **Critical Contradiction**, reasoning: *"If a pickup is scheduled for the future, the ticket cannot be closed."*
* **Root Cause of AI Error:**
  * The LLM lacked domain context of NYC 311 Standard Operating Procedures (SOP): DSNY automatically marks missed collection complaints as closed as soon as a work order pickup is dispatched to the route schedule.
* **How It Was Caught:**
  * Caught during **Phase 1 clean baseline testing** (`test_project_b.py`). When testing on 100% clean historical records, the LLM had a **1.5% false-alarm rate**, whereas deterministic rules and statistical detectors had **0.00% false alarms**.
* **Architectural Lesson:**
  * LLMs are prone to false alarms when semantic domain nuances differ from general language training. This justified placing the LLM as Tier 3 in the hybrid cascade, used only on pre-filtered rows rather than as an indiscriminate gatekeeper.
