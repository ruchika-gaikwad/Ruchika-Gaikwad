"""
tax_utils.py
Utility helper functions for the Indian Income Tax Engine.
Provides:
- Currency formatting (Indian numbering system: lakhs and crores)
- Rule file loading and validation
- Result comparison between Rule, LLM, and Hybrid engines
- Audit trail generator tracing every rupee to Income Tax Act clauses
- Performance metrics (accuracy, latency, and cost per 1,000 requests)
"""

import json
import os
import time
from typing import Dict, Any, List, Optional, Tuple


def format_inr(amount: float, use_symbol: bool = False) -> str:
    """
    Formats a number into the Indian numbering format (e.g., 12,50,000.00).
    """
    prefix = "₹" if use_symbol else "Rs. "
    if amount is None:
        return f"{prefix}0.00"

    is_negative = amount < 0
    amount = abs(amount)

    s, *d = f"{amount:.2f}".split(".")
    cents = f".{d[0]}" if d else ""

    if len(s) <= 3:
        formatted = s
    else:
        last_three = s[-3:]
        remaining = s[:-3]
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        groups.append(last_three)
        formatted = ",".join(groups)

    sign = "-" if is_negative else ""
    return f"{sign}{prefix}{formatted}{cents}"


def load_tax_rules(year: str = "2024-25") -> Dict[str, Any]:
    """
    Safely loads tax rules from the data folder for the given financial year.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = f"tax_rules_{year.replace('-', '_')}.json"
    file_path = os.path.join(base_dir, "data", filename)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Tax rules file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_gemini_api_key() -> Optional[str]:
    """
    Retrieves GEMINI_API_KEY from environment or .env file.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(base_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    val = line.split("GEMINI_API_KEY=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        os.environ["GEMINI_API_KEY"] = val
                        return val
    return None


def compare_calculations(
    ground_truth: Dict[str, Any],
    candidate: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compares a candidate calculation (e.g., from an LLM) against ground truth rules.
    Returns exact rupee difference and boolean match flag.
    """
    gt_old = ground_truth.get("old_regime", {}).get("total_tax_payable", 0)
    cand_old = candidate.get("old_regime", {}).get("total_tax_payable", 0)
    diff_old = abs(gt_old - cand_old)

    gt_new = ground_truth.get("new_regime", {}).get("total_tax_payable", 0)
    cand_new = candidate.get("new_regime", {}).get("total_tax_payable", 0)
    diff_new = abs(gt_new - cand_new)

    gt_rec = ground_truth.get("recommended_regime", "").strip().lower()
    cand_rec = candidate.get("recommended_regime", "").strip().lower()
    rec_match = gt_rec == cand_rec

    is_exact_match = (diff_old == 0) and (diff_new == 0) and rec_match

    return {
        "exact_match": is_exact_match,
        "old_regime_diff": diff_old,
        "new_regime_diff": diff_new,
        "recommendation_match": rec_match,
        "ground_truth_old": gt_old,
        "candidate_old": cand_old,
        "ground_truth_new": gt_new,
        "candidate_new": cand_new
    }


def generate_audit_trail(regime_calc: Dict[str, Any]) -> List[str]:
    """
    Generates a legal audit trail linking each computation line to specific
    sections of the Indian Income-tax Act, 1961.
    """
    audit = []
    regime = regime_calc.get("regime", "")
    gross = regime_calc.get("gross_salary", 0)
    std_ded = regime_calc.get("standard_deduction", 0)

    audit.append(f"Gross Salary Income: {format_inr(gross)}")
    audit.append(f"Less: Standard Deduction u/s 16(ia): {format_inr(std_ded)}")

    if "Old" in regime:
        hra = regime_calc.get("hra_exemption", 0)
        c = regime_calc.get("section_80c", 0)
        ccd = regime_calc.get("section_80ccd_1b", 0)
        d = regime_calc.get("section_80d", 0)
        hl = regime_calc.get("section_24b_home_loan_interest", 0)

        if hra > 0:
            audit.append(f"Less: HRA Exemption u/s 10(13A) read with Rule 2A: {format_inr(hra)}")
        if c > 0:
            audit.append(f"Less: Deduction u/s 80C (Capped at Rs. 1,50,000): {format_inr(c)}")
        if ccd > 0:
            audit.append(f"Less: NPS Self-Contribution u/s 80CCD(1B) (Capped at Rs. 50,000): {format_inr(ccd)}")
        if d > 0:
            audit.append(f"Less: Health Insurance u/s 80D: {format_inr(d)}")
        if hl > 0:
            audit.append(f"Less: Loss from Self-Occupied House Property u/s 24(b) (Capped at Rs. 2,00,000): {format_inr(hl)}")

    net_inc = regime_calc.get("net_taxable_income", 0)
    audit.append(f"Net Taxable Income (Rounded u/s 288A): {format_inr(net_inc)}")

    slab_tax = regime_calc.get("slab_tax", 0)
    audit.append(f"Base Income Tax under progressive slabs: {format_inr(slab_tax)}")

    rebate = regime_calc.get("rebate_87a", 0)
    if rebate > 0:
        audit.append(f"Less: Tax Rebate u/s 87A: -{format_inr(rebate)}")

    surcharge = regime_calc.get("surcharge", 0)
    if surcharge > 0:
        relief = regime_calc.get("marginal_relief_surcharge", 0)
        audit.append(f"Add: Surcharge (net of marginal relief {format_inr(relief)}): +{format_inr(surcharge)}")

    cess = regime_calc.get("cess_4_percent", 0)
    audit.append(f"Add: Health & Education Cess @ 4%: +{format_inr(cess)}")

    total = regime_calc.get("total_tax_payable", 0)
    audit.append(f"Total Tax Payable (Rounded u/s 288B): {format_inr(total)}")

    return audit


if __name__ == "__main__":
    # Test tax_utils directly
    rules = load_tax_rules("2024-25")
    print(f"Loaded rules for FY {rules['financial_year']} (AY {rules['assessment_year']})")
    print("Currency sample:", format_inr(1250000.75))
