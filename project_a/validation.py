"""
validation.py
Data Validation and Sanity Engine for Indian Income Tax Inputs.
Handles Task 3 requirements:
- Validates extracted salary and deduction parameters.
- Catches missing information and ambiguous inputs.
- Catches contradictory inputs (e.g., basic > gross, 80C > 1.5L, rent=0 with HRA).
- Formulates precise clarifying questions instead of guessing.
"""

from typing import Dict, Any, List, Tuple


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely converts any value (including None or invalid string) to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


class TaxInputValidator:
    """
    Validates user financial inputs against physical logic and statutory IT rules.
    """

    @staticmethod
    def validate(profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates a structured taxpayer profile.
        Returns validation status, cleaned parameters, and any clarifying questions.
        """
        errors: List[str] = []
        warnings: List[str] = []
        clarifying_questions: List[str] = []

        # 1. Gross Salary Validation
        gross_val = profile.get("gross_salary")
        if gross_val is None or safe_float(gross_val, -1.0) < 0:
            clarifying_questions.append(
                "Please specify your annual gross salary or CTC to compute tax."
            )
            return {
                "status": "INCOMPLETE",
                "is_valid": False,
                "clarifying_questions": clarifying_questions,
                "warnings": warnings,
                "cleaned_profile": {}
            }

        gross = safe_float(gross_val)

        # 2. Basic Salary Validation & Contradiction Check
        basic_val = profile.get("basic_salary")
        rent_paid = safe_float(profile.get("rent_paid"))
        hra_received = safe_float(profile.get("hra_received"))

        if basic_val is not None:
            basic = safe_float(basic_val)
            if basic > gross:
                clarifying_questions.append(
                    f"Contradiction detected: Basic salary (Rs. {basic:,.2f}) cannot exceed "
                    f"gross salary (Rs. {gross:,.2f}). Please verify your salary breakdown."
                )
                return {
                    "status": "CONTRADICTORY",
                    "is_valid": False,
                    "clarifying_questions": clarifying_questions,
                    "warnings": warnings,
                    "cleaned_profile": profile
                }
        else:
            # Default basic to 50% of gross if HRA is not claimed, else flag for clarification
            if rent_paid > 0 or hra_received > 0:
                clarifying_questions.append(
                    "You indicated rent/HRA. What is your exact Basic Salary so we can "
                    "calculate your statutory Section 10(13A) HRA exemption accurately?"
                )
            basic = gross * 0.50

        # 3. HRA and Rent Paid Validation
        is_metro = bool(profile.get("is_metro", False))

        if hra_received > gross:
            clarifying_questions.append(
                f"Contradiction: HRA received (Rs. {hra_received:,.2f}) cannot be greater than "
                f"total gross salary (Rs. {gross:,.2f})."
            )
            return {
                "status": "CONTRADICTORY",
                "is_valid": False,
                "clarifying_questions": clarifying_questions,
                "warnings": warnings,
                "cleaned_profile": profile
            }

        if hra_received > 0 and rent_paid == 0:
            warnings.append(
                "Notice: You receive HRA but pay Rs. 0 rent. Under Section 10(13A) Rule 2A, "
                "HRA is fully taxable unless actual rent is paid with receipts."
            )

        # 4. Section 80C Deduction Check
        sec_80c = safe_float(profile.get("section_80c"))
        if sec_80c > 150000.0:
            warnings.append(
                f"Section 80C declaration of Rs. {sec_80c:,.2f} exceeds the statutory ceiling. "
                "The engine will automatically cap this deduction at Rs. 1,50,000."
            )
            sec_80c = 150000.0
        elif sec_80c > gross:
            clarifying_questions.append(
                f"Contradiction: Section 80C investment (Rs. {sec_80c:,.2f}) cannot exceed your "
                f"entire gross salary (Rs. {gross:,.2f}). Did you intend a different amount?"
            )
            return {
                "status": "CONTRADICTORY",
                "is_valid": False,
                "clarifying_questions": clarifying_questions,
                "warnings": warnings,
                "cleaned_profile": profile
            }

        # 5. Section 80CCD(1B) NPS Check
        sec_80ccd = safe_float(profile.get("section_80ccd_1b"))
        if sec_80ccd > 50000.0:
            warnings.append(
                f"Section 80CCD(1B) NPS deduction of Rs. {sec_80ccd:,.2f} exceeds the statutory "
                "ceiling. The engine will automatically cap this deduction at Rs. 50,000."
            )
            sec_80ccd = 50000.0

        # 6. Section 80D Health Insurance Check
        d_self = safe_float(profile.get("section_80d_self"))
        self_sr = bool(profile.get("self_senior", False))
        self_cap = 50000.0 if self_sr else 25000.0
        if d_self > self_cap:
            warnings.append(
                f"Section 80D (Self) premium of Rs. {d_self:,.2f} exceeds statutory cap of "
                f"Rs. {self_cap:,.2f}. Deduction will be capped at Rs. {self_cap:,.2f}."
            )
            d_self = self_cap

        d_parents = safe_float(profile.get("section_80d_parents"))
        parents_sr = bool(profile.get("parents_senior", False))
        parents_cap = 50000.0 if parents_sr else 25000.0
        if d_parents > parents_cap:
            warnings.append(
                f"Section 80D (Parents) premium of Rs. {d_parents:,.2f} exceeds statutory cap of "
                f"Rs. {parents_cap:,.2f}. Deduction will be capped at Rs. {parents_cap:,.2f}."
            )
            d_parents = parents_cap

        prev_checkup = min(safe_float(profile.get("preventive_checkup")), 5000.0)

        # 7. Section 24(b) Home Loan Interest Check
        hl_interest = safe_float(profile.get("home_loan_interest_24b"))
        if hl_interest > 200000.0:
            warnings.append(
                f"Section 24(b) home loan interest of Rs. {hl_interest:,.2f} exceeds the maximum "
                "permissible loss of Rs. 2,00,000 for a self-occupied property. Capped at Rs. 2,00,000."
            )
            hl_interest = 200000.0

        # Build Cleaned and Normalized Profile
        cleaned = {
            "gross_salary": gross,
            "basic_salary": basic,
            "hra_received": hra_received,
            "rent_paid": rent_paid,
            "is_metro": is_metro,
            "section_80c": sec_80c,
            "section_80ccd_1b": sec_80ccd,
            "section_80d_self": d_self,
            "self_senior": self_sr,
            "section_80d_parents": d_parents,
            "parents_senior": parents_sr,
            "preventive_checkup": prev_checkup,
            "home_loan_interest_24b": hl_interest,
            "residential_status": profile.get("residential_status", "resident"),
            "age_category": profile.get("age_category", "below_60"),
            "age": profile.get("age", None)
        }

        status = "NEEDS_CLARIFICATION" if clarifying_questions else "VALID"

        return {
            "status": status,
            "is_valid": len(clarifying_questions) == 0,
            "clarifying_questions": clarifying_questions,
            "warnings": warnings,
            "cleaned_profile": cleaned
        }


if __name__ == "__main__":
    validator = TaxInputValidator()

    # Test 1: Valid Profile with statutory caps needed
    valid_test = {
        "gross_salary": 1500000.0,
        "basic_salary": 750000.0,
        "section_80c": 180000.0,  # exceeds 1.5L
        "home_loan_interest_24b": 250000.0  # exceeds 2L
    }
    res1 = validator.validate(valid_test)
    print("--- Test 1: Valid Profile with Warnings ---")
    print("Status  :", res1["status"])
    print("Valid   :", res1["is_valid"])
    print("Warnings:", res1["warnings"])
    print("Cleaned 80C : Rs.", res1["cleaned_profile"]["section_80c"])
    print("Cleaned 24b : Rs.", res1["cleaned_profile"]["home_loan_interest_24b"])

    # Test 2: Contradictory Profile (basic > gross)
    contradictory_test = {
        "gross_salary": 800000.0,
        "basic_salary": 1000000.0  # Impossible!
    }
    res2 = validator.validate(contradictory_test)
    print("\n--- Test 2: Contradictory Input ---")
    print("Status   :", res2["status"])
    print("Question :", res2["clarifying_questions"])

    # Test 3: Incomplete Profile (missing gross salary)
    incomplete_test = {
        "section_80c": 150000.0
    }
    res3 = validator.validate(incomplete_test)
    print("\n--- Test 3: Incomplete Input ---")
    print("Status   :", res3["status"])
    print("Question :", res3["clarifying_questions"])
