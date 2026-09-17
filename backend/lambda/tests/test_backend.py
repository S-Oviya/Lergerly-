"""
Unit tests for Ledgerly Lambda Handler and Ledger Service.
Runs locally using Python standard library (unittest) without AWS credentials.
"""

import os
import sys
import json
import unittest
from decimal import Decimal
from unittest.mock import patch

# Ensure backend/lambda is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, ".."))
if lambda_dir not in sys.path:
    sys.path.insert(0, lambda_dir)

import handler
from services.ledger_service import LedgerService


class TestLedgerServiceBalance(unittest.TestCase):
    """Tests deterministic financial calculations in the ledger service."""

    def test_deterministic_balance_calculation(self):
        """
        Rule: balance = total CREDIT - total PAYMENT
        credits 500 + 250, payment 300 -> balance 450
        """
        service = LedgerService()
        with patch.object(service, "get_customer_transactions") as mock_get_txs:
            mock_get_txs.return_value = [
                {"type": "CREDIT", "amount": Decimal("500")},
                {"type": "CREDIT", "amount": Decimal("250")},
                {"type": "PAYMENT", "amount": Decimal("300")},
            ]
            calculated_balance = service.calculate_customer_balance("customer_test_001")
            self.assertEqual(calculated_balance, Decimal("450"))


class TestLambdaHandlerValidation(unittest.TestCase):
    """Tests API Gateway request handling and payload validation."""

    def test_valid_post_message(self):
        """Valid POST /message returns 200 with status received."""
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"message": "Rahul took rice for 500 on credit"}),
        }
        response = handler.lambda_handler(event)
        self.assertEqual(response["statusCode"], 200)

        body = json.loads(response["body"])
        self.assertTrue(body["success"])
        self.assertEqual(body["message"], "Rahul took rice for 500 on credit")
        self.assertEqual(body["status"], "received")

    def test_missing_message_field(self):
        """Missing 'message' field returns 400 Bad Request."""
        event = {
            "httpMethod": "POST",
            "body": json.dumps({}),
        }
        response = handler.lambda_handler(event)
        self.assertEqual(response["statusCode"], 400)

        body = json.loads(response["body"])
        self.assertFalse(body["success"])
        self.assertIn("Field 'message' is required", body["error"])

    def test_empty_message_field(self):
        """Empty or whitespace-only 'message' field returns 400 Bad Request."""
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"message": "    "}),
        }
        response = handler.lambda_handler(event)
        self.assertEqual(response["statusCode"], 400)

        body = json.loads(response["body"])
        self.assertFalse(body["success"])
        self.assertIn("Field 'message' cannot be empty", body["error"])

    def test_invalid_customer_payload(self):
        """Customer creation missing required fields (e.g. phone) returns 400 Bad Request."""
        event = {
            "httpMethod": "POST",
            "path": "/customers",
            "body": json.dumps({
                "shopId": "shop001",
                "name": "Rahul",
                # missing "phone"
            }),
        }
        response = handler.lambda_handler(event)
        self.assertEqual(response["statusCode"], 400)

        body = json.loads(response["body"])
        self.assertFalse(body["success"])
        self.assertIn("phone", body["error"])

    def test_invalid_transaction_type(self):
        """Transaction with unsupported type returns 400 Bad Request."""
        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "body": json.dumps({
                "shopId": "shop001",
                "customerId": "cust001",
                "type": "INVALID_TRANSFER",
                "amount": 500,
            }),
        }
        response = handler.lambda_handler(event)
        self.assertEqual(response["statusCode"], 400)

        body = json.loads(response["body"])
        self.assertFalse(body["success"])
        self.assertIn("Transaction type must be CREDIT or PAYMENT", body["error"])

    def test_invalid_transaction_amount(self):
        """Transaction with non-positive amount returns 400 Bad Request."""
        event = {
            "httpMethod": "POST",
            "path": "/transactions",
            "body": json.dumps({
                "shopId": "shop001",
                "customerId": "cust001",
                "type": "CREDIT",
                "amount": 0,
            }),
        }
        response = handler.lambda_handler(event)
        self.assertEqual(response["statusCode"], 400)

        body = json.loads(response["body"])
        self.assertFalse(body["success"])
        self.assertIn("amount must be greater than zero", body["error"])


if __name__ == "__main__":
    unittest.main()
