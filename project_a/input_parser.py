"""
input_parser.py
Natural Language Understanding (NLU) Parser for Indian Income Tax Queries.
Handles Task 3:
- Extracts structured financial parameters from plain English, casual text, and Hinglish.
- Normalizes monthly vs annual figures (e.g., '15k rent per month' -> 1,80,000 annual).
- Normalizes Indian units ('12 LPA', '1.5 lakh', '50k', '2.5 Crore').
- Detects missing or ambiguous information and generates clarifying questions instead of guessing.
- Features Gemini API integration with an offline rule-heuristic fallback.
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from project_a.validation import TaxInputValidator
from project_a.tax_utils import get_gemini_api_key


PARSER_SYSTEM_PROMPT = """You are an expert financial entity extractor for Indian salaried income tax.
Your job is to read user statements (in formal English, casual English, or Hinglish) and extract structured numbers.

EXTRACTION RULES:
1. Always convert all salary and deduction numbers into ANNUAL amounts in INR (Rupees):
   - '12 LPA' or '12 lakh' or '12L' = 1200000.
   - '50k per month' or '50,000 pm' = 50000 * 12 = 600000.
   - '20k rent monthly' = 20000 * 12 = 240000.
   - '1.5L 80C' = 150000.
   - '1 Crore' or '1 Cr' = 10000000.
2. Metro cities for HRA under IT Rule 2A are strictly: Delhi, Mumbai, Kolkata, Chennai. (Bengaluru, Pune, Hyderabad, Gurgaon are Non-Metro).
3. If parents are mentioned as senior citizens (elderly, 60+, retired, mummy papa senior), set 'parents_senior': true.
4. DO NOT GUESS missing numbers.
   - If gross salary / CTC is not provided, mark 'is_incomplete': true and provide a specific 'clarifying_question'.
   - If user asks a vague question (e.g. 'I make 10L, how much tax?'), set 'is_incomplete': true and ask if they have rent or 80C deductions.
   - If user provides contradictory numbers (e.g. basic > gross, or 80C > gross), mark 'is_contradictory': true and explain the conflict.

OUTPUT JSON FORMAT ONLY:
{
  "gross_salary": float or null,
  "basic_salary": float or null,
  "hra_received": float,
  "rent_paid": float,
  "is_metro": boolean,
  "section_80c": float,
  "section_80ccd_1b": float,
  "section_80d_self": float,
  "self_senior": boolean,
  "section_80d_parents": float,
  "parents_senior": boolean,
  "preventive_checkup": float,
  "home_loan_interest_24b": float,
  "is_incomplete": boolean,
  "is_contradictory": boolean,
  "clarifying_question": string or null
}
"""


class PlainLanguageParser:
    """
    Parses plain-language user queries into validated structured financial profiles.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3.1-flash-lite"):
        self.api_key = api_key or get_gemini_api_key()
        self.model = model
        self.validator = TaxInputValidator()

    def _call_gemini_nlu(self, user_text: str) -> Dict[str, Any]:
        """
        Sends user text to Gemini API for entity extraction.
        """
        candidate_models = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": PARSER_SYSTEM_PROMPT},
                        {"text": f"User query:\n\"{user_text}\"\n\nExtract parameters to strict JSON:"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "response_mime_type": "application/json"
            }
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        last_error = None

        for current_model in candidate_models:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={self.api_key}"
            req = urllib.request.Request(
                endpoint,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    res_body = resp.read().decode("utf-8")
                    api_response = json.loads(res_body)
                    self.model = current_model
                    break
            except Exception as e:
                last_error = e
                continue
        else:
            raise RuntimeError(f"Gemini API error across models: {last_error}")

        candidate = api_response["candidates"][0]
        raw_text = candidate["content"]["parts"][0]["text"].strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        return json.loads(raw_text.strip())

    def _offline_heuristic_parse(self, user_text: str) -> Dict[str, Any]:
        """
        Robust regex and heuristic fallback parser when GEMINI_API_KEY is not set.
        Understands LPA, lakhs, monthly rent, Hinglish keywords, and common deductions.
        """
        text = user_text.lower()
        extracted: Dict[str, Any] = {
            "gross_salary": None,
            "basic_salary": None,
            "hra_received": 0.0,
            "rent_paid": 0.0,
            "is_metro": False,
            "section_80c": 0.0,
            "section_80ccd_1b": 0.0,
            "section_80d_self": 0.0,
            "self_senior": False,
            "section_80d_parents": 0.0,
            "parents_senior": False,
            "preventive_checkup": 0.0,
            "home_loan_interest_24b": 0.0,
            "is_incomplete": False,
            "is_contradictory": False,
            "clarifying_question": None
        }

        # 1. Metro detection
        if any(m in text for m in ["delhi", "mumbai", "kolkata", "chennai"]):
            extracted["is_metro"] = True

        # 2. Extract Basic Salary first if mentioned explicitly
        basic_match = re.search(r"basic\s*(?:salary)?\s*(?:is|of)?\s*(?:only|around|approx|about)?\s*(?:rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:lpa|lakh|lac|l\b)?", text)
        if basic_match:
            val_str = basic_match.group(1).replace(",", "")
            val = float(val_str)
            if "lpa" in text or "lakh" in text or "lac" in text or val <= 100.0:
                extracted["basic_salary"] = val * 100000.0 if val <= 100.0 else val
            else:
                extracted["basic_salary"] = val

        # 3. Extract Gross Salary (e.g., 'total gross salary is rs 8,00,000', '12 lpa', '15 lakh', 'ctc 18 lakh')
        cr_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:crore|cr\b)", text)
        if cr_match:
            extracted["gross_salary"] = float(cr_match.group(1)) * 10000000.0
        else:
            gross_match = re.search(r"(?:total\s*(?:gross\s*)?salary|gross\s*(?:salary)?|ctc|package|annual\s*salary|income|make)\s*(?:is|of)?\s*(?:only|around|approx|about)?\s*(?:rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:lpa|lakh|lac|l\b)?", text)
            if not gross_match:
                # Fallback to standalone salary if not basic
                gross_match = re.search(r"(?<!basic\s)salary\s*(?:is|of)?\s*(?:only|around|approx|about)?\s*(?:rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:lpa|lakh|lac|l\b)?", text)

            if gross_match:
                val_str = gross_match.group(1).replace(",", "")
                val = float(val_str)
                if val <= 100.0:  # e.g. 12 or 8.5
                    extracted["gross_salary"] = val * 100000.0
                else:
                    extracted["gross_salary"] = val

        # 4. Extract Rent Paid (e.g. '15,000 rent deta hu monthly', 'paying 20k rent')
        rent_match = re.search(r"(\d+(?:,\d+)?|\d+k?)\s*(?:rent|pm rent|monthly rent|rent deta hu)", text)
        if not rent_match:
            rent_match = re.search(r"rent\s*(?:paid|is|of|deta hu)?\s*(?:rs\.?|inr)?\s*(\d+(?:,\d+)?|\d+k?)", text)

        if rent_match:
            val_str = rent_match.group(1).replace(",", "")
            val = float(val_str.replace("k", "")) * 1000 if "k" in val_str else float(val_str)
            if "month" in text or "pm" in text or val < 100000:
                extracted["rent_paid"] = val * 12.0
            else:
                extracted["rent_paid"] = val

        # 5. Extract HRA received
        hra_match = re.search(r"hra\s*(?:received|milta hai|is|of)?\s*(?:rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:lpa|lakh|lac|l\b)?", text)
        if hra_match:
            val_str = hra_match.group(1).replace(",", "")
            val = float(val_str)
            extracted["hra_received"] = val * 100000.0 if val <= 100.0 else val

        # 6. Extract Section 80C
        c_match = re.search(r"(?:80c\s*(?:me)?|ppf|lic|pf)\s*.*?(\d+(?:\.\d+)?)\s*(?:lakh|lac|l\b|k\b)?", text)
        if not c_match:
            c_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|l\b|k\b)?\s*(?:80c|invest|in 80c)", text)
        if c_match:
            raw_val = float(c_match.group(1))
            if raw_val <= 10.0:
                extracted["section_80c"] = raw_val * 100000.0
            elif raw_val <= 150.0:
                extracted["section_80c"] = raw_val * 1000.0
            else:
                extracted["section_80c"] = raw_val

        # 7. Extract NPS 80CCD(1B)
        if "nps" in text or "80ccd" in text:
            nps_match = re.search(r"(?:nps|80ccd\(1b\)|80ccd)\s*(?:me|is|of)?\s*(\d+(?:\.\d+)?)\s*(?:lakh|lac|l\b|k\b)?", text)
            if nps_match:
                val = float(nps_match.group(1))
                extracted["section_80ccd_1b"] = val * 1000.0 if "k" in text else (val * 100000.0 if val <= 5.0 else val)

        # 8. Extract Health Insurance Section 80D
        if "senior" in text or "mummy papa" in text or "parents" in text:
            extracted["parents_senior"] = True
            d_par_match = re.search(r"(?:parents|mummy papa|senior).*?(\d+(?:,\d+)?|\d+k)", text)
            if d_par_match:
                val_str = d_par_match.group(1).replace(",", "")
                val = float(val_str.replace("k", "")) * 1000 if "k" in val_str else float(val_str)
                extracted["section_80d_parents"] = val

        if "insurance self" in text or "mediclaim" in text or "health insurance" in text:
            d_self_match = re.search(r"(?:health insurance|mediclaim|self)\s*(?:of|is|rs\.?|inr)?\s*(\d+(?:,\d+)?|\d+k)", text)
            if d_self_match:
                val_str = d_self_match.group(1).replace(",", "")
                val = float(val_str.replace("k", "")) * 1000 if "k" in val_str else float(val_str)
                extracted["section_80d_self"] = val

        # 9. Extract Home Loan Interest Section 24(b)
        hl_match = re.search(r"(?:home loan|housing loan)\s*(?:interest)?\s*.*?(\d+(?:\.\d+)?)\s*(?:lakh|lac|l\b|k\b)?", text)
        if hl_match:
            val = float(hl_match.group(1))
            extracted["home_loan_interest_24b"] = val * 100000.0 if val <= 10.0 else val

        # 10. Incomplete / Missing Check
        if extracted["gross_salary"] is None:
            extracted["is_incomplete"] = True
            extracted["clarifying_question"] = "Please provide your annual gross salary or CTC to compute your tax liability."

        return extracted

    def parse(self, user_text: str) -> Dict[str, Any]:
        """
        Parses text input into a validated profile.
        Uses Gemini NLU if API key is set, otherwise uses the heuristic parser.
        Then feeds the extracted profile into TaxInputValidator.
        """
        start_time = time.time()
        is_live_api = bool(self.api_key)

        if is_live_api:
            try:
                extracted = self._call_gemini_nlu(user_text)
            except Exception as e:
                # Gracefully fall back to heuristic parser on API error
                extracted = self._offline_heuristic_parse(user_text)
                extracted["api_notice"] = f"Fell back to heuristic parser: {str(e)}"
        else:
            extracted = self._offline_heuristic_parse(user_text)

        elapsed_ms = (time.time() - start_time) * 1000

        # Pass extracted data through deterministic Python validation
        validation_result = self.validator.validate(extracted)

        # Merge clarifying questions from NLU and Validator
        all_questions = list(validation_result["clarifying_questions"])
        if extracted.get("clarifying_question") and extracted["clarifying_question"] not in all_questions:
            all_questions.insert(0, extracted["clarifying_question"])

        status = validation_result["status"]
        if extracted.get("is_incomplete") and status != "CONTRADICTORY":
            status = "INCOMPLETE"

        return {
            "raw_text": user_text,
            "status": status,
            "is_valid": len(all_questions) == 0,
            "extracted_profile": validation_result["cleaned_profile"],
            "clarifying_questions": all_questions,
            "warnings": validation_result["warnings"],
            "metadata": {
                "parser_engine": "Gemini-1.5-Flash NLU" if is_live_api else "Heuristic Pattern Extractor",
                "latency_ms": elapsed_ms
            }
        }


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    parser = PlainLanguageParser()

    print("=" * 65)
    print("TASK 3: PLAIN-LANGUAGE INPUT PARSER (ENGLISH & HINGLISH)")
    print("=" * 65)

    test_queries = [
        # Query 1: Hinglish complete
        "Mera annual CTC 12 lakh hai. Delhi me rehta hu aur 15,000 rent deta hu monthly. HRA company se 2,40,000 milta hai. 80C me 1.5L invest kiya hai.",
        # Query 2: Incomplete query
        "I make 10 lakhs. How much tax?",
        # Query 3: Contradictory query
        "My basic salary is Rs 10,00,000 but my total gross salary is Rs 8,00,000."
    ]

    for idx, query in enumerate(test_queries, 1):
        print(f"\n[Test Case {idx}] User Query:")
        print(f"\"{query}\"")
        res = parser.parse(query)
        print(f"Status      : {res['status']}")
        print(f"Is Valid    : {res['is_valid']}")
        if res["clarifying_questions"]:
            print(f"Questions   : {res['clarifying_questions']}")
        else:
            p = res["extracted_profile"]
            print(f"Extracted   : Gross=Rs. {p['gross_salary']:,}, Rent=Rs. {p['rent_paid']:,}, 80C=Rs. {p['section_80c']:,}, Metro={p['is_metro']}")
        print(f"Parser Engine: {res['metadata']['parser_engine']} ({res['metadata']['latency_ms']:.2f} ms)")
        print("-" * 65)
