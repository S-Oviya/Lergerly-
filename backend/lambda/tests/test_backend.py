"""
Unit tests for Ledgerly Lambda Handler, Ledger Service, and Bedrock Extraction Service.
Runs locally using Python standard library (unittest) without requiring live AWS credentials.
"""

import os
import sys
import io
import json
import unittest
from decimal import Decimal
from unittest.mock import patch, MagicMock

# Ensure backend/lambda is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, ".."))
if lambda_dir not in sys.path:
    sys.path.insert(0, lambda_dir)

import handler
from services.ledger_service import LedgerService
from services.bedrock_service import (
    BedrockService,
    BedrockUnavailableError,
    BedrockExtractionError,
)


class TestLedgerServiceBalance(unittest.TestCase):
    """Tests deterministic financial calculations in the ledger service."""

    def test_deterministic_balance_calculation(self):
        """
        Rule: balance = total CREDIT - total PAYMENT
        credits 500 + 250, payment 300 -> balance 450
        Strictly deterministic; never computed by AI.
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


class TestBedrockExtractionService(unittest.TestCase):
    """Tests Amazon Bedrock transaction entity extraction and validation."""

    def _create_mock_response(self, text_content: str):
        """Helper to create a boto3 invoke_model response structure for Claude 3."""
        payload = {
            "content": [
                {"type": "text", "text": text_content}
            ]
        }
        return {"body": io.BytesIO(json.dumps(payload).encode("utf-8"))}

    def test_extract_credit_purchase(self):
        """
        Input: 'Rahul took rice for 500 on credit'
        Expected: CREDIT / 500 / Rahul / rice
        """
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = self._create_mock_response(
            json.dumps({
                "customerName": "Rahul",
                "type": "CREDIT",
                "amount": 500,
                "description": "rice"
            })
        )

        service = BedrockService(client=mock_client)
        result = service.extract_transaction("Rahul took rice for 500 on credit")

        self.assertEqual(result["customerName"], "Rahul")
        self.assertEqual(result["type"], "CREDIT")
        self.assertEqual(result["amount"], 500)
        self.assertEqual(result["description"], "rice")

    def test_extract_payment_settlement(self):
        """
        Input: 'Rahul paid 300'
        Expected: PAYMENT / 300 / Rahul / ''
        """
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = self._create_mock_response(
            json.dumps({
                "customerName": "Rahul",
                "type": "PAYMENT",
                "amount": 300,
                "description": ""
            })
        )

        service = BedrockService(client=mock_client)
        result = service.extract_transaction("Rahul paid 300")

        self.assertEqual(result["customerName"], "Rahul")
        self.assertEqual(result["type"], "PAYMENT")
        self.assertEqual(result["amount"], 300)
        self.assertEqual(result["description"], "")

    def test_invalid_model_response_non_json(self):
        """Invalid model response (non-JSON text) raises BedrockExtractionError."""
        service = BedrockService()
        with self.assertRaises(BedrockExtractionError) as ctx:
            service.parse_and_validate_extraction("I am an AI and I cannot parse this.")
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_invalid_model_response_empty(self):
        """Empty model response raises BedrockExtractionError."""
        service = BedrockService()
        with self.assertRaises(BedrockExtractionError) as ctx:
            service.parse_and_validate_extraction("   ")
        self.assertIn("empty response", str(ctx.exception))

    def test_invalid_transaction_type(self):
        """Transaction type other than CREDIT or PAYMENT raises BedrockExtractionError."""
        service = BedrockService()
        invalid_json = json.dumps({
            "customerName": "Rahul",
            "type": "TRANSFER",
            "amount": 500,
            "description": "rice"
        })
        with self.assertRaises(BedrockExtractionError) as ctx:
            service.parse_and_validate_extraction(invalid_json)
        self.assertIn("Unsupported transaction type", str(ctx.exception))

    def test_invalid_transaction_amount_zero_or_negative(self):
        """Non-positive amount raises BedrockExtractionError."""
        service = BedrockService()
        invalid_json = json.dumps({
            "customerName": "Rahul",
            "type": "CREDIT",
            "amount": -50,
            "description": "rice"
        })
        with self.assertRaises(BedrockExtractionError) as ctx:
            service.parse_and_validate_extraction(invalid_json)
        self.assertIn("Amount must be greater than zero", str(ctx.exception))

    def test_invalid_transaction_amount_non_numeric(self):
        """Non-numeric amount raises BedrockExtractionError."""
        service = BedrockService()
        invalid_json = json.dumps({
            "customerName": "Rahul",
            "type": "CREDIT",
            "amount": "five hundred",
            "description": "rice"
        })
        with self.assertRaises(BedrockExtractionError) as ctx:
            service.parse_and_validate_extraction(invalid_json)
        self.assertIn("Amount must be a numeric value", str(ctx.exception))

    def test_missing_customer_name(self):
        """Missing or empty customerName raises BedrockExtractionError."""
        service = BedrockService()
        invalid_json = json.dumps({
            "customerName": "",
            "type": "CREDIT",
            "amount": 500,
            "description": "rice"
        })
        with self.assertRaises(BedrockExtractionError) as ctx:
            service.parse_and_validate_extraction(invalid_json)
        self.assertIn("customerName", str(ctx.exception))


class TestLambdaHandlerValidation(unittest.TestCase):
    """Tests API Gateway request handling, validation, and Bedrock integration."""

    @patch.object(handler.bedrock_service, "extract_transaction")
    def test_valid_post_message(self, mock_extract):
        """Valid POST /message calls Bedrock and returns 200 with extracted transaction."""
        mock_extract.return_value = {
            "customerName": "Rahul",
            "type": "CREDIT",
            "amount": 500,
            "description": "rice",
        }
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
        self.assertEqual(body["extractedTransaction"]["customerName"], "Rahul")
        self.assertEqual(body["extractedTransaction"]["type"], "CREDIT")
        self.assertEqual(body["extractedTransaction"]["amount"], 500)
        self.assertEqual(body["extractedTransaction"]["description"], "rice")

    @patch.object(handler.bedrock_service, "extract_transaction")
    def test_post_message_bedrock_unavailable(self, mock_extract):
        """When Bedrock is unreachable or unconfigured, returns 503 Service Unavailable."""
        mock_extract.side_effect = BedrockUnavailableError("Unable to locate credentials")
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"message": "Rahul took rice for 500 on credit"}),
        }
        response = handler.lambda_handler(event)
        self.assertEqual(response["statusCode"], 503)

        body = json.loads(response["body"])
        self.assertFalse(body["success"])
        self.assertIn("Amazon Bedrock service is unavailable", body["error"])

    @patch.object(handler.bedrock_service, "extract_transaction")
    def test_post_message_bedrock_extraction_error(self, mock_extract):
        """When Bedrock extraction fails validation, returns 400 Bad Request."""
        mock_extract.side_effect = BedrockExtractionError("Model output is not valid JSON")
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"message": "unintelligible audio"}),
        }
        response = handler.lambda_handler(event)
        self.assertEqual(response["statusCode"], 400)

        body = json.loads(response["body"])
        self.assertFalse(body["success"])
        self.assertIn("Transaction extraction failed", body["error"])

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
