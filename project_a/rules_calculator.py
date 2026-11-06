"""
rules_calculator.py
Deterministic Rule-Based Income Tax Calculator for Salaried Individuals in India.
Covers Financial Year 2024-25 (Assessment Year 2025-26).

Legal references:
- Income-tax Act, 1961
- Finance (No. 2) Act, 2024
- Official Income Tax Department slabs, rebate, surcharge, and cess rules
"""

import json
import math
import os
from typing import Dict, Any, Tuple, Optional


def round_to_nearest_10(amount: float) -> int:
    """
    Rounds an amount to the nearest multiple of Rs. 10 as per Sections 288A and 288B
    of the Indian Income Tax Act.
    If the last digit is 5 or more, it rounds up to the higher multiple of 10.
    """
    return int(math.floor((amount + 5) / 10.0) * 10)


def calculate_hra_exemption(
    basic_salary: float,
    hra_received: float,
    rent_paid: float,
    is_metro: bool = False
) -> Dict[str, Any]:
    """
    Calculates HRA exemption under Section 10(13A) read with Rule 2A.
    Exemption is the minimum of:
      1. Actual HRA received
      2. Rent paid minus 10% of Basic Salary
      3. 50% of Basic Salary (if Metro: Delhi, Mumbai, Kolkata, Chennai)
         or 40% of Basic Salary (Non-Metro)
    """
    rent_minus_10_percent = max(0.0, rent_paid - (0.10 * basic_salary))
    salary_limit_percent = 0.50 if is_metro else 0.40
    basic_percentage_limit = salary_limit_percent * basic_salary

    exemption = min(hra_received, rent_minus_10_percent, basic_percentage_limit)
    exemption = max(0.0, exemption)

    return {
        "hra_received": hra_received,
        "rent_minus_10_percent_basic": rent_minus_10_percent,
        "salary_percentage_limit": basic_percentage_limit,
        "is_metro": is_metro,
        "exempt_hra": exemption,
        "taxable_hra": max(0.0, hra_received - exemption)
    }


def calculate_80d_deduction(
    self_family_premium: float = 0.0,
    self_senior: bool = False,
    parents_premium: float = 0.0,
    parents_senior: bool = False,
    preventive_health_checkup: float = 0.0
) -> Dict[str, Any]:
    """
    Calculates health insurance deduction under Section 80D.
    - Self/Spouse/Children: Limit Rs. 25,000 (Rs. 50,000 if senior citizen >= 60 yrs).
    - Parents: Limit Rs. 25,000 (Rs. 50,000 if parents senior citizen >= 60 yrs).
    - Preventive health checkup: Overall combined cap of Rs. 5,000 within the limits.
    """
    # Preventive checkup is capped at 5000 overall
    usable_preventive = min(preventive_health_checkup, 5000.0)

    # First allocate preventive checkup to self/family, remainder to parents
    self_limit = 50000.0 if self_senior else 25000.0
    parents_limit = 50000.0 if parents_senior else 25000.0

    # Self & family eligible amount
    self_total = self_family_premium + usable_preventive
    self_allowed = min(self_total, self_limit)

    # Any unused preventive checkup limit (within Rs. 5000) can cover parents
    used_preventive_self = max(0.0, min(usable_preventive, self_allowed - self_family_premium))
    remaining_preventive = max(0.0, usable_preventive - used_preventive_self)

    parents_total = parents_premium + remaining_preventive
    parents_allowed = min(parents_total, parents_limit)

    total_80d = self_allowed + parents_allowed

    return {
        "self_family_allowed": self_allowed,
        "self_senior": self_senior,
        "parents_allowed": parents_allowed,
        "parents_senior": parents_senior,
        "preventive_checkup_used": usable_preventive,
        "total_80d_deduction": total_80d
    }


def calculate_base_slab_tax(income: float, slabs: list) -> Tuple[float, list]:
    """
    Computes tax using progressive income tax slabs.
    Returns the total tax and the breakdown for each slab.
    """
    tax = 0.0
    breakdown = []

    for slab in slabs:
        min_val = slab["min"]
        max_val = slab["max"]
        rate = slab["rate"]

        if income > min_val:
            if max_val is not None:
                taxable_in_slab = min(income, max_val) - min_val
            else:
                taxable_in_slab = income - min_val

            slab_tax = taxable_in_slab * rate
            tax += slab_tax
            breakdown.append({
                "slab": f"Rs. {min_val:,} - {'Above' if max_val is None else f'Rs. {max_val:,}'}",
                "rate": f"{int(rate * 100)}%",
                "taxable_amount": taxable_in_slab,
                "tax": slab_tax
            })
        else:
            breakdown.append({
                "slab": f"Rs. {min_val:,} - {'Above' if max_val is None else f'Rs. {max_val:,}'}",
                "rate": f"{int(rate * 100)}%",
                "taxable_amount": 0.0,
                "tax": 0.0
            })

    return tax, breakdown


def calculate_surcharge_and_relief(
    income: float,
    tax: float,
    surcharge_slabs: list,
    regime: str,
    rules: dict
) -> Tuple[float, float, float]:
    """
    Calculates Surcharge and applicable Marginal Relief.
    Marginal relief ensures:
    Total tax + surcharge does not exceed:
    (Tax on threshold + amount of income exceeding threshold).
    """
    applicable_rate = 0.0
    threshold = 0.0

    # Determine highest applicable surcharge rate
    for slab in surcharge_slabs:
        if income > slab["threshold"]:
            if slab["rate"] > applicable_rate:
                applicable_rate = slab["rate"]
                threshold = slab["threshold"]

    if applicable_rate == 0.0:
        return 0.0, 0.0, 0.0

    raw_surcharge = tax * applicable_rate

    # Calculate tax payable at the threshold
    if regime == "old":
        slabs = rules["old_regime"]["slabs"]
    else:
        slabs = rules["new_regime"]["slabs"]

    tax_at_threshold, _ = calculate_base_slab_tax(threshold, slabs)

    # Check surcharge rate at threshold (if any)
    lower_surcharge_rate = 0.0
    for slab in surcharge_slabs:
        if slab["threshold"] < threshold and threshold > slab["threshold"]:
            if slab["rate"] > lower_surcharge_rate:
                lower_surcharge_rate = slab["rate"]

    surcharge_at_threshold = tax_at_threshold * lower_surcharge_rate
    total_payable_at_threshold = tax_at_threshold + surcharge_at_threshold

    # Maximum tax and surcharge allowed under marginal relief provisions
    excess_income = income - threshold
    max_allowed = total_payable_at_threshold + excess_income

    current_total = tax + raw_surcharge
    marginal_relief = max(0.0, current_total - max_allowed)
    effective_surcharge = max(0.0, raw_surcharge - marginal_relief)

    return applicable_rate, effective_surcharge, marginal_relief


class SalariedTaxEngine:
    """
    Official Indian Salaried Income Tax Engine for FY 2024-25 (AY 2025-26).
    Compares Old and New Tax Regimes with rupee-exact precision.
    """

    def __init__(self, config_path: Optional[str] = None, year: str = "2024-25"):
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            filename = f"tax_rules_{year.replace('-', '_')}.json"
            config_path = os.path.join(base_dir, "data", filename)

        with open(config_path, "r", encoding="utf-8") as f:
            self.rules = json.load(f)
        self.year = self.rules.get("financial_year", year)

    def calculate_old_regime(
        self,
        gross_salary: float,
        basic_salary: float = 0.0,
        hra_received: float = 0.0,
        rent_paid: float = 0.0,
        is_metro: bool = False,
        section_80c: float = 0.0,
        section_80ccd_1b: float = 0.0,
        section_80d_self: float = 0.0,
        self_senior: bool = False,
        section_80d_parents: float = 0.0,
        parents_senior: bool = False,
        preventive_checkup: float = 0.0,
        home_loan_interest_24b: float = 0.0,
        age_category: str = "below_60",
        is_resident: bool = True
    ) -> Dict[str, Any]:
        """
        Calculates tax under the Old Tax Regime for salaried individuals.
        """
        rules_old = self.rules["old_regime"]

        # 1. Standard deduction (Sec 16(ia)): Flat 50,000 or gross salary, whichever is lower
        std_deduction_limit = rules_old["standard_deduction"]
        std_deduction = min(gross_salary, float(std_deduction_limit))

        # 2. HRA exemption (Sec 10(13A))
        hra_calc = calculate_hra_exemption(basic_salary, hra_received, rent_paid, is_metro)
        exempt_hra = min(hra_calc["exempt_hra"], gross_salary - std_deduction)

        # 3. Chapter VI-A Deductions
        allowed_80c = min(section_80c, rules_old["deductions"]["section_80c_cap"])
        allowed_80ccd_1b = min(section_80ccd_1b, rules_old["deductions"]["section_80ccd_1b_cap"])

        health_calc = calculate_80d_deduction(
            self_family_premium=section_80d_self,
            self_senior=self_senior,
            parents_premium=section_80d_parents,
            parents_senior=parents_senior,
            preventive_health_checkup=preventive_checkup
        )
        allowed_80d = health_calc["total_80d_deduction"]

        # 4. Section 24(b) Home loan interest (self-occupied house max Rs. 2,00,000)
        allowed_24b = min(home_loan_interest_24b, rules_old["deductions"]["section_24b_home_loan_interest_cap"])

        # 5. Total deductions & Net Taxable Income
        total_deductions = std_deduction + exempt_hra + allowed_80c + allowed_80ccd_1b + allowed_80d + allowed_24b
        net_taxable_income = max(0.0, gross_salary - total_deductions)
        net_taxable_income_rounded = round_to_nearest_10(net_taxable_income)

        # 6. Base Slab Tax (Select slabs based on age category for Old Regime)
        if age_category == "super_senior":
            # 80 years and above (Super Senior Citizen): Nil up to Rs. 5,00,000
            slabs = [
                {"min": 0, "max": 500000, "rate": 0.0},
                {"min": 500000, "max": 1000000, "rate": 0.20},
                {"min": 1000000, "max": None, "rate": 0.30}
            ]
        elif age_category == "senior" or self_senior:
            # 60 to 79 years (Senior Citizen): Nil up to Rs. 3,00,000
            slabs = [
                {"min": 0, "max": 300000, "rate": 0.0},
                {"min": 300000, "max": 500000, "rate": 0.05},
                {"min": 500000, "max": 1000000, "rate": 0.20},
                {"min": 1000000, "max": None, "rate": 0.30}
            ]
        else:
            slabs = rules_old["slabs"]

        base_tax, slab_breakdown = calculate_base_slab_tax(net_taxable_income_rounded, slabs)

        # 7. Section 87A Rebate (Available only to Resident individuals)
        sec_87a_limit = rules_old["section_87a"]["income_limit"]
        sec_87a_max = rules_old["section_87a"]["max_rebate"]
        rebate_87a = 0.0

        if is_resident and net_taxable_income_rounded <= sec_87a_limit:
            rebate_87a = min(base_tax, float(sec_87a_max))

        tax_after_rebate = max(0.0, base_tax - rebate_87a)

        # 8. Surcharge & Marginal Relief
        surcharge_rate, surcharge, marginal_relief_surcharge = calculate_surcharge_and_relief(
            income=net_taxable_income_rounded,
            tax=tax_after_rebate,
            surcharge_slabs=rules_old["surcharge"],
            regime="old",
            rules=self.rules
        )

        tax_with_surcharge = tax_after_rebate + surcharge

        # 9. Health & Education Cess (4%)
        cess_rate = self.rules["health_and_education_cess_rate"]
        cess = tax_with_surcharge * cess_rate

        # 10. Total Tax Payable (rounded to nearest 10 as per Sec 288B)
        total_tax = round_to_nearest_10(tax_with_surcharge + cess)

        return {
            "regime": "Old Tax Regime",
            "gross_salary": gross_salary,
            "standard_deduction": std_deduction,
            "hra_exemption": exempt_hra,
            "section_80c": allowed_80c,
            "section_80ccd_1b": allowed_80ccd_1b,
            "section_80d": allowed_80d,
            "section_24b_home_loan_interest": allowed_24b,
            "total_deductions": total_deductions,
            "net_taxable_income": net_taxable_income_rounded,
            "slab_tax": base_tax,
            "slab_breakdown": slab_breakdown,
            "rebate_87a": rebate_87a,
            "tax_after_rebate": tax_after_rebate,
            "surcharge_rate": surcharge_rate,
            "surcharge": surcharge,
            "marginal_relief_surcharge": marginal_relief_surcharge,
            "cess_4_percent": cess,
            "total_tax_payable": total_tax
        }

    def calculate_new_regime(self, gross_salary: float, is_resident: bool = True) -> Dict[str, Any]:
        """
        Calculates tax under the New Tax Regime (Section 115BAC) for salaried individuals.
        For FY 2024-25:
          - Standard Deduction: Rs. 75,000 (hiked in Finance Act 2024)
          - Section 87A Rebate: Zero tax up to Rs. 7,00,000 net income (Residents only), with marginal relief
            for income marginally exceeding Rs. 7,00,000.
          - Slabs are uniform across all age brackets.
        """
        rules_new = self.rules["new_regime"]

        # 1. Standard deduction: Rs. 75,000 for FY 2024-25
        std_deduction_limit = rules_new["standard_deduction"]
        std_deduction = min(gross_salary, float(std_deduction_limit))

        # 2. Net Taxable Income
        net_taxable_income = max(0.0, gross_salary - std_deduction)
        net_taxable_income_rounded = round_to_nearest_10(net_taxable_income)

        # 3. Base Slab Tax
        base_tax, slab_breakdown = calculate_base_slab_tax(net_taxable_income_rounded, rules_new["slabs"])

        # 4. Section 87A Rebate & Marginal Relief (Residents only)
        sec_87a_limit = rules_new["section_87a"]["income_limit"]
        sec_87a_max = rules_new["section_87a"]["max_rebate"]
        rebate_87a = 0.0
        marginal_relief_87a = 0.0

        if is_resident:
            if net_taxable_income_rounded <= sec_87a_limit:
                rebate_87a = min(base_tax, float(sec_87a_max))
            else:
                # Proviso to Section 87A: Tax payable cannot exceed excess income over Rs. 7,00,000
                excess_income = net_taxable_income_rounded - sec_87a_limit
                if base_tax > excess_income:
                    marginal_relief_87a = base_tax - excess_income
                    rebate_87a = marginal_relief_87a

        tax_after_rebate = max(0.0, base_tax - rebate_87a)

        # 5. Surcharge & Marginal Relief
        surcharge_rate, surcharge, marginal_relief_surcharge = calculate_surcharge_and_relief(
            income=net_taxable_income_rounded,
            tax=tax_after_rebate,
            surcharge_slabs=rules_new["surcharge"],
            regime="new",
            rules=self.rules
        )

        tax_with_surcharge = tax_after_rebate + surcharge

        # 6. Health & Education Cess (4%)
        cess_rate = self.rules["health_and_education_cess_rate"]
        cess = tax_with_surcharge * cess_rate

        # 7. Total Tax Payable (rounded to nearest 10 as per Sec 288B)
        total_tax = round_to_nearest_10(tax_with_surcharge + cess)

        return {
            "regime": "New Tax Regime (Sec 115BAC)",
            "gross_salary": gross_salary,
            "standard_deduction": std_deduction,
            "total_deductions": std_deduction,
            "net_taxable_income": net_taxable_income_rounded,
            "slab_tax": base_tax,
            "slab_breakdown": slab_breakdown,
            "rebate_87a": rebate_87a,
            "marginal_relief_87a": marginal_relief_87a,
            "tax_after_rebate": tax_after_rebate,
            "surcharge_rate": surcharge_rate,
            "surcharge": surcharge,
            "marginal_relief_surcharge": marginal_relief_surcharge,
            "cess_4_percent": cess,
            "total_tax_payable": total_tax
        }

    def compare_regimes(self, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Computes tax under both Old and New regimes, identifies the recommended regime,
        and provides an audit trail explaining the difference.
        Supports:
          - Residential Status: Resident (default) vs Non-Resident
          - Age Category: Below 60 (Regular), 60-79 (Senior), 80+ (Super Senior)
        """
        gross_salary = float(user_profile.get("gross_salary", 0.0))

        # 1. Parse Residential Status
        is_resident = bool(user_profile.get("is_resident", True))
        if "residential_status" in user_profile:
            status_val = str(user_profile["residential_status"]).lower()
            is_resident = status_val in ["resident", "res", "true", "1"]

        # 2. Parse Age Category
        age_cat = user_profile.get("age_category", "below_60")
        age = user_profile.get("age", None)
        if age is not None:
            try:
                age_num = float(age)
                if age_num >= 80:
                    age_cat = "super_senior"
                elif age_num >= 60:
                    age_cat = "senior"
                else:
                    age_cat = "below_60"
            except (ValueError, TypeError):
                pass

        self_senior = bool(user_profile.get("self_senior", False)) or (age_cat in ["senior", "super_senior"])

        old_calc = self.calculate_old_regime(
            gross_salary=gross_salary,
            basic_salary=float(user_profile.get("basic_salary", 0.0)),
            hra_received=float(user_profile.get("hra_received", 0.0)),
            rent_paid=float(user_profile.get("rent_paid", 0.0)),
            is_metro=bool(user_profile.get("is_metro", False)),
            section_80c=float(user_profile.get("section_80c", 0.0)),
            section_80ccd_1b=float(user_profile.get("section_80ccd_1b", 0.0)),
            section_80d_self=float(user_profile.get("section_80d_self", 0.0)),
            self_senior=self_senior,
            section_80d_parents=float(user_profile.get("section_80d_parents", 0.0)),
            parents_senior=bool(user_profile.get("parents_senior", False)),
            preventive_checkup=float(user_profile.get("preventive_checkup", 0.0)),
            home_loan_interest_24b=float(user_profile.get("home_loan_interest_24b", 0.0)),
            age_category=age_cat,
            is_resident=is_resident
        )

        new_calc = self.calculate_new_regime(gross_salary=gross_salary, is_resident=is_resident)

        old_tax = old_calc["total_tax_payable"]
        new_tax = new_calc["total_tax_payable"]

        if old_tax < new_tax:
            recommended = "Old Tax Regime"
            savings = new_tax - old_tax
            reason = (
                f"Old Regime saves you Rs. {savings:,} because your total deductions "
                f"(Rs. {old_calc['total_deductions']:,}) exceed the breakeven threshold."
            )
        elif new_tax < old_tax:
            recommended = "New Tax Regime"
            savings = old_tax - new_tax
            reason = (
                f"New Regime saves you Rs. {savings:,} due to lower tax slab rates "
                f"and Rs. 75,000 standard deduction, despite fewer itemized exemptions."
            )
        else:
            recommended = "Either Regime"
            savings = 0
            reason = "Both regimes result in the exact same tax liability."

        return {
            "recommended_regime": recommended,
            "tax_savings": savings,
            "explanation": reason,
            "old_regime": old_calc,
            "new_regime": new_calc
        }


if __name__ == "__main__":
    import sys
    # Ensure stdout handles UTF-8 on Windows
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # Sample Test: An employee with Gross Salary Rs. 12,00,000
    sample_employee = {
        "gross_salary": 1200000.0,
        "basic_salary": 600000.0,
        "hra_received": 240000.0,
        "rent_paid": 180000.0,
        "is_metro": True,
        "section_80c": 150000.0,
        "section_80ccd_1b": 50000.0,
        "section_80d_self": 25000.0,
        "self_senior": False,
        "section_80d_parents": 50000.0,
        "parents_senior": True,
        "preventive_checkup": 5000.0,
        "home_loan_interest_24b": 200000.0
    }

    engine = SalariedTaxEngine()
    result = engine.compare_regimes(sample_employee)

    print("=" * 60)
    print("INDIAN INCOME TAX ENGINE (FY 2024-25 / AY 2025-26)")
    print("=" * 60)
    print(f"Gross Salary: Rs. {sample_employee['gross_salary']:,.2f}")
    print("-" * 60)
    print(f"OLD REGIME Total Tax  : Rs. {result['old_regime']['total_tax_payable']:,.2f}")
    print(f"  - Total Deductions  : Rs. {result['old_regime']['total_deductions']:,.2f}")
    print(f"  - Net Taxable Income: Rs. {result['old_regime']['net_taxable_income']:,.2f}")
    print("-" * 60)
    print(f"NEW REGIME Total Tax  : Rs. {result['new_regime']['total_tax_payable']:,.2f}")
    print(f"  - Standard Deduction: Rs. {result['new_regime']['standard_deduction']:,.2f}")
    print(f"  - Net Taxable Income: Rs. {result['new_regime']['net_taxable_income']:,.2f}")
    print("-" * 60)
    print(f"RECOMMENDATION        : {result['recommended_regime']}")
    print(f"TAX SAVINGS           : Rs. {result['tax_savings']:,.2f}")
    print(f"EXPLANATION           : {result['explanation']}")
    print("=" * 60)
