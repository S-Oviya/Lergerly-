"""
Ledgerly - Payment Reply Service
Deterministic parser for customer WhatsApp payment replies.

Recognizes customer payment confirmations such as:
- "I paid ₹500"
- "paid 500"
- "₹500 paid"
- "payment done 500"
- "payment made 500"
- "I have paid Rs 500"
- "I've paid ₹1,000"
- "paid Rs. 750"
- "payment of ₹500 done"
- Hindi/Hinglish: "500 jama kiya", "bhugtan 500"

Safely flags ambiguous cases without valid amounts (e.g. "paid", "settled", "paid 0")
and returns None for normal transaction notes (e.g. "Rahul bought rice for ₹500").
"""

import re
from typing import Any, Dict, Optional


class PaymentReplyService:
    """
    Lightweight, deterministic parser for incoming customer payment replies.
    Does NOT calculate balances or directly modify storage.
    """

    # First-person and auxiliary prefixes to identify customer self-reports
    FIRST_PERSON_PREFIXES = {"i", "ive", "i've", "we", "weve", "we've", "maine", "mene", "humne", "hamne"}
    AUX_OR_ADVERBS = {"have", "had", "has", "already", "just", "recently", "also", "and", "then", "now", "am", "is", "was"}

    # Keywords indicating a payment action
    PAYMENT_KEYWORD_REGEX = re.compile(
        r"\b(paid|payment|pay|settled|cleared|jama|bhugtan|deposit)\b",
        re.IGNORECASE,
    )

    # Patterns to extract the payment amount
    AMOUNT_PATTERNS = [
        # Pattern 1: Currency prefix followed by amount (e.g., "₹500", "Rs 500", "Rs. 750", "INR 1,000")
        re.compile(
            r"(?:₹|rs\.?|inr)\s*([+-]?[\d,]+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
        # Pattern 2: Verb / phrase followed by optional payee/preposition and amount (e.g., "paid 500", "I paid Rahul 500", "paid to Rahul ₹500")
        re.compile(
            r"\b(?:paid|payment|pay|done|made|jama|bhugtan|deposit)\b(?:\s+(?:to|for|of|done|made|ko|bhai|bhaiya|dukaan|shop|[a-zA-Z]+)){0,3}\s*(?:₹|rs\.?|inr)?\s*([+-]?[\d,]+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
        # Pattern 3: Amount followed by currency/unit and verb (e.g., "500 paid", "500 payment done", "500 jama")
        re.compile(
            r"([+-]?[\d,]+(?:\.\d+)?)\s*(?:(?:rupees|rs\.?|₹|inr)\s*)?\b(?:paid|payment|done|made|jama|bhugtan|settled|cleared)\b",
            re.IGNORECASE,
        ),
    ]

    def _is_third_person_subject(self, text: str) -> bool:
        """
        Checks if the statement begins with a 3rd-person name acting as the subject who paid,
        e.g. 'Rahul paid 300' or 'Suresh paid 500'.
        Such statements are shopkeeper transaction notes (not customer self-reports)
        and must route to Bedrock extraction.
        """
        tokens = text.strip().split()
        for i, tok in enumerate(tokens):
            clean_tok = tok.lower().strip(".,!?")
            if clean_tok in ("paid", "pay", "jama", "bhugtan") and i > 0:
                prev = tokens[i - 1].lower().strip(".,!?")
                clean_prev = re.sub(r"^[₹$]|^(rs\.?|inr)", "", prev, flags=re.IGNORECASE).strip()
                if not clean_prev or re.match(r"^[+-]?[\d,]+(?:\.\d+)?$", clean_prev) or prev in ("rs", "rs.", "rupees", "inr"):
                    continue
                if prev not in self.FIRST_PERSON_PREFIXES and prev not in self.AUX_OR_ADVERBS:
                    return True
        return False

    def parse(
        self,
        text: str,
        customer_name: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Parses incoming message text for customer payment replies.

        Returns:
            - Dict with action="PAYMENT", amount, customerName, source="whatsapp" on clear match.
            - Dict with action="AMBIGUOUS", amount=None on payment intent without valid amount.
            - None if the message is not a payment reply (normal transaction flow).
        """
        if not isinstance(text, str):
            return None

        cleaned = text.strip()
        if not cleaned:
            return None

        # If 3rd-person subject is detected (e.g. 'Rahul paid 300'), route to Bedrock transaction extraction
        if self._is_third_person_subject(cleaned):
            return None

        # If no payment keywords are found, it's not a payment reply (e.g. "Rahul bought rice for ₹500")
        if not self.PAYMENT_KEYWORD_REGEX.search(cleaned):
            return None

        # Attempt to extract numeric amount
        found_amount: Optional[Any] = None
        for regex in self.AMOUNT_PATTERNS:
            match = regex.search(cleaned)
            if match:
                raw_num = match.group(1).replace(",", "")
                try:
                    val = float(raw_num)
                    # Reject zero and negative amounts
                    if val > 0:
                        # Return int if whole number, otherwise float
                        found_amount = int(val) if val.is_integer() else val
                        break
                    else:
                        found_amount = "INVALID"
                        break
                except (ValueError, TypeError):
                    continue

        if found_amount == "INVALID" or found_amount is None:
            # Payment keyword present but no valid positive amount found -> AMBIGUOUS
            result: Dict[str, Any] = {
                "action": "AMBIGUOUS",
                "amount": None,
                "customerName": customer_name,
                "source": "whatsapp",
            }
            if language:
                result["language"] = language
            return result

        # Clear positive payment detected
        result = {
            "action": "PAYMENT",
            "amount": found_amount,
            "customerName": customer_name,
            "source": "whatsapp",
        }
        if language:
            result["language"] = language
        return result
