"""
hybrid_calculator.py
Hybrid Income Tax Engine for Salaried Individuals in India (FY 2024-25).
Combines:
  1. Plain-Language NLU (Gemini / Heuristic Parser) to understand natural user queries.
  2. Deterministic Python Validator to enforce statutory limits and guardrails.
  3. Deterministic Python Rules Engine to calculate rupee-exact tax liability.
  4. Natural Language Explanation Generator with a legal audit trail.

This represents the winning production architecture:
LLMs used only where they excel (natural language understanding & explanation),
and Python code used where it excels (arithmetic precision, statutory caps, 100% determinism).
"""

import json
import os
import sys
import time
from typing import Dict, Any, Optional, Union

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from project_a.input_parser import PlainLanguageParser
from project_a.rules_calculator import SalariedTaxEngine
from project_a.tax_utils import format_inr, generate_audit_trail


class HybridTaxCalculator:
    """
    Production-grade Hybrid Income Tax Pipeline.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.parser = PlainLanguageParser(api_key=api_key)
        self.engine = SalariedTaxEngine()

    def process(self, user_input: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes the hybrid pipeline:
        1. If user_input is a string, parses natural language into structured parameters.
        2. Validates inputs and catches missing/contradictory data.
        3. If clarification is needed, pauses and asks the user rather than guessing.
        4. If valid, computes rupee-exact tax using deterministic Python rules.
        5. Generates a clear, user-friendly explanation with statutory audit trail.
        """
        start_time = time.time()

        # Step 1: Input Parsing
        if isinstance(user_input, str):
            parse_result = self.parser.parse(user_input)
            raw_text = user_input
        else:
            # If structured dictionary already passed
            raw_text = None
            val_res = self.parser.validator.validate(user_input)
            parse_result = {
                "raw_text": None,
                "status": val_res["status"],
                "is_valid": val_res["is_valid"],
                "extracted_profile": val_res["cleaned_profile"],
                "clarifying_questions": val_res["clarifying_questions"],
                "warnings": val_res["warnings"],
                "metadata": {"parser_engine": "Direct Structured Input", "latency_ms": 0.0}
            }

        # Step 2: Guardrail Check (Missing or Contradictory Information)
        if not parse_result["is_valid"]:
            elapsed_ms = (time.time() - start_time) * 1000
            return {
                "success": False,
                "status": parse_result["status"],
                "clarifying_questions": parse_result["clarifying_questions"],
                "warnings": parse_result["warnings"],
                "extracted_profile": parse_result["extracted_profile"],
                "raw_input": raw_text,
                "pipeline_latency_ms": elapsed_ms,
                "message": (
                    "We need a quick clarification before we can calculate your tax accurately. "
                    "Please answer the clarifying question(s) above."
                )
            }

        # Step 3: Deterministic Rule-Based Calculation
        profile = parse_result["extracted_profile"]
        calc_result = self.engine.compare_regimes(profile)

        # Step 4: Audit Trails
        old_audit = generate_audit_trail(calc_result["old_regime"])
        new_audit = generate_audit_trail(calc_result["new_regime"])

        # Step 5: Natural Language Explanation Generation
        old_tax = calc_result["old_regime"]["total_tax_payable"]
        new_tax = calc_result["new_regime"]["total_tax_payable"]
        recommended = calc_result["recommended_regime"]
        savings = calc_result["tax_savings"]
        gross = profile["gross_salary"]
        deductions = calc_result["old_regime"]["total_deductions"]

        if recommended == "Old Tax Regime":
            explanation = (
                f"For your gross salary of {format_inr(gross)}, the Old Tax Regime is significantly better. "
                f"You save {format_inr(savings)} in taxes! This is because your itemized deductions and exemptions "
                f"total {format_inr(deductions)} (including standard deduction, HRA, and Chapter VI-A investments), "
                f"which substantially reduces your taxable income below the New Regime equivalent."
            )
        elif recommended == "New Tax Regime":
            explanation = (
                f"For your gross salary of {format_inr(gross)}, the New Tax Regime (Section 115BAC) is the better choice. "
                f"You save {format_inr(savings)} in taxes! Thanks to the expanded Rs. 75,000 standard deduction and "
                f"lower slab rates across every income bracket, the New Regime outperforms the Old Regime for your deduction level."
            )
        else:
            explanation = (
                f"For your income level of {format_inr(gross)}, both Old and New Tax Regimes result in the exact same "
                f"tax liability ({format_inr(old_tax)}). You may opt for either regime."
            )

        elapsed_ms = (time.time() - start_time) * 1000

        return {
            "success": True,
            "status": "CALCULATED",
            "recommended_regime": recommended,
            "tax_savings": savings,
            "human_explanation": explanation,
            "old_regime_tax": old_tax,
            "new_regime_tax": new_tax,
            "warnings": parse_result["warnings"],
            "cleaned_profile": profile,
            "full_calculation": calc_result,
            "audit_trail": {
                "old_regime": old_audit,
                "new_regime": new_audit
            },
            "pipeline_latency_ms": elapsed_ms,
            "raw_input": raw_text
        }


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    hybrid_engine = HybridTaxCalculator()

    print("=" * 68)
    print("TASK 3: COMPLETE HYBRID INCOME TAX ENGINE (FY 2024-25)")
    print("=" * 68)

    sample_queries = [
        # Query 1: Complete Hinglish with deductions
        "Mera annual package 14 lakh hai. Basic 7 lakh, HRA 3L, Delhi me 25k monthly rent deta hu. 80C me 1.5 lakh invest kiya hai aur senior citizen parents ke liye 50k health insurance.",
        # Query 2: Incomplete query (requires clarification)
        "I make 12 LPA. Which regime should I choose?",
        # Query 3: Contradictory query
        "My basic salary is Rs 9,00,000 but my total gross salary is only Rs 7,00,000."
    ]

    for idx, q in enumerate(sample_queries, 1):
        print(f"\n[Case {idx}] User Input: \"{q}\"")
        res = hybrid_engine.process(q)

        if not res["success"]:
            print(f"Status    : {res['status']}")
            print(f"Action    : System detected missing/contradictory info and pauses for clarification.")
            print(f"Questions : {res['clarifying_questions']}")
        else:
            print(f"Status              : {res['status']}")
            print(f"Recommended Regime  : {res['recommended_regime']}")
            print(f"Tax Savings         : {format_inr(res['tax_savings'])}")
            print(f"Old Regime Tax      : {format_inr(res['old_regime_tax'])}")
            print(f"New Regime Tax      : {format_inr(res['new_regime_tax'])}")
            print(f"Explanation         : {res['human_explanation']}")
            print("Audit Trail (Old Regime Top Clauses):")
            for line in res["audit_trail"]["old_regime"][:4]:
                print(f"  - {line}")

        print(f"Pipeline Latency: {res['pipeline_latency_ms']:.2f} ms")
        print("-" * 68)
