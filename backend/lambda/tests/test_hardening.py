"""
Unit tests for Ledgerly Backend Hardening:
1. Webhook Idempotency (prevent duplicate ledger entries on Meta webhook retries).
2. WhatsApp Send Retry & Exponential Backoff (handle transient 429/5xx Graph API errors).
3. Configuration Validation (feature-scoped validation without breaking offline tests).
4. AWS Throttling / Transient Failure Handling (bounded backoff on Bedrock & Transcribe).
"""

import io
import json
import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, call, patch
import urllib.error

# Ensure backend/lambda is on sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, ".."))
if lambda_dir not in sys.path:
    sys.path.insert(0, lambda_dir)

import handler
from services.config import (
    ConfigValidationError,
    validate_bedrock_config,
    validate_dynamodb_config,
    validate_environment,
    validate_transcribe_config,
    validate_whatsapp_config,
)
from services.ledger_service import LedgerService
from services.retry_helper import (
    is_aws_transient_error,
    retry_with_backoff,
)
from services.whatsapp_service import (
    WhatsAppService,
    WhatsAppUnavailableError,
    WhatsAppValidationError,
    is_transient_whatsapp_error,
)
from services.bedrock_service import (
    BedrockService,
    BedrockUnavailableError,
)
from services.transcribe_service import (
    TranscribeService,
    TranscribeUnavailableError,
)


class TestWebhookIdempotency(unittest.TestCase):
    """Verifies that duplicate WhatsApp webhooks do not duplicate transactions."""

    def setUp(self):
        # Clean environment
        self.patcher_send = patch.object(handler.whatsapp_service, "send_text")
        self.mock_send = self.patcher_send.start()
        self.mock_send.return_value = {"messages": [{"id": "wa_reply_001"}]}

    def tearDown(self):
        self.patcher_send.stop()

    @patch.object(handler.bedrock_service, "extract_transaction")
    @patch.object(handler.ledger_service, "list_customers")
    @patch.object(handler.ledger_service, "get_customer_transactions")
    @patch.object(handler.ledger_service, "add_transaction")
    @patch.object(handler.ledger_service, "calculate_customer_balance")
    def test_normal_transaction_duplicate_webhook_is_idempotent(
        self,
        mock_calc_bal,
        mock_add_tx,
        mock_get_txs,
        mock_list_cust,
        mock_extract,
    ):
        """
        When Meta delivers the same webhook twice for a purchase note:
        - First delivery creates the transaction.
        - Second delivery detects existing transaction 'wa_<msg_id>', skips add_transaction,
          and returns duplicate=True with deterministic balance.
        """
        mock_list_cust.return_value = [{"customerId": "cust_123", "name": "Rahul", "phone": "919876543210"}]
        mock_extract.return_value = {
            "customerName": "Rahul",
            "type": "CREDIT",
            "amount": 500,
            "description": "rice",
        }
        mock_calc_bal.return_value = Decimal("500")

        # Simulate first webhook delivery
        mock_get_txs.return_value = []
        mock_add_tx.return_value = {
            "transactionId": "wa_msg_test_001",
            "type": "CREDIT",
            "amount": 500,
            "updatedCustomerBalance": 500,
        }

        event = {
            "httpMethod": "POST",
            "path": "/whatsapp/webhook",
            "body": json.dumps({
                "object": "whatsapp_business_account",
                "entry": [{
                    "changes": [{
                        "value": {
                            "metadata": {"phone_number_id": "phone_123"},
                            "messages": [{
                                "from": "919876543210",
                                "id": "msg_test_001",
                                "type": "text",
                                "text": {"body": "Rahul took rice for 500 on credit"},
                            }]
                        }
                    }]
                }]
            })
        }

        resp1 = handler.lambda_handler(event)
        self.assertEqual(resp1["statusCode"], 200)
        body1 = json.loads(resp1["body"])
        self.assertTrue(body1["success"])
        res1 = body1["results"][0]
        self.assertEqual(res1["status"], "processed")
        self.assertFalse(res1.get("duplicate", False))
        self.assertEqual(mock_add_tx.call_count, 1)

        # Simulate second webhook delivery with the exact same message_id
        existing_tx = {
            "transactionId": "wa_msg_test_001",
            "type": "CREDIT",
            "amount": Decimal("500"),
            "customerId": "cust_123",
            "shopId": "shop001",
        }
        mock_get_txs.return_value = [existing_tx]

        resp2 = handler.lambda_handler(event)
        self.assertEqual(resp2["statusCode"], 200)
        body2 = json.loads(resp2["body"])
        self.assertTrue(body2["success"])
        res2 = body2["results"][0]
        self.assertEqual(res2["status"], "processed")
        self.assertTrue(res2.get("duplicate"))
        # Crucial: add_transaction must NOT be called a second time!
        self.assertEqual(mock_add_tx.call_count, 1)

    @patch.object(handler.ledger_service, "list_customers")
    @patch.object(handler.ledger_service, "get_customer_transactions")
    @patch.object(handler.ledger_service, "add_transaction")
    @patch.object(handler.ledger_service, "calculate_customer_balance")
    def test_payment_reply_duplicate_webhook_is_idempotent(
        self,
        mock_calc_bal,
        mock_add_tx,
        mock_get_txs,
        mock_list_cust,
    ):
        """
        When Meta delivers the same payment reply webhook twice:
        - First creates the payment transaction.
        - Second delivery detects 'wa_<msg_id>', skips adding, flags duplicate=True.
        """
        mock_list_cust.return_value = [{"customerId": "cust_pay_1", "name": "Suresh", "phone": "919876543210"}]
        mock_calc_bal.return_value = Decimal("200")
        mock_get_txs.return_value = []
        mock_add_tx.return_value = {
            "transactionId": "wa_pay_msg_999",
            "type": "PAYMENT",
            "amount": 300,
            "updatedCustomerBalance": 200,
        }

        event = {
            "httpMethod": "POST",
            "path": "/whatsapp/webhook",
            "body": json.dumps({
                "object": "whatsapp_business_account",
                "entry": [{
                    "changes": [{
                        "value": {
                            "metadata": {"phone_number_id": "phone_123"},
                            "messages": [{
                                "from": "919876543210",
                                "id": "pay_msg_999",
                                "type": "text",
                                "text": {"body": "I paid 300"},
                            }]
                        }
                    }]
                }]
            })
        }

        # 1st delivery
        resp1 = handler.lambda_handler(event)
        self.assertEqual(resp1["statusCode"], 200)
        body1 = json.loads(resp1["body"])
        res1 = body1["results"][0]
        self.assertEqual(res1["status"], "processed")
        self.assertFalse(res1.get("duplicate", False))
        self.assertEqual(mock_add_tx.call_count, 1)

        # 2nd delivery (re-delivered webhook)
        mock_get_txs.return_value = [{
            "transactionId": "wa_pay_msg_999",
            "type": "PAYMENT",
            "amount": Decimal("300"),
        }]

        resp2 = handler.lambda_handler(event)
        self.assertEqual(resp2["statusCode"], 200)
        body2 = json.loads(resp2["body"])
        res2 = body2["results"][0]
        self.assertEqual(res2["status"], "processed")
        self.assertTrue(res2.get("duplicate"))
        # add_transaction should not be called again
        self.assertEqual(mock_add_tx.call_count, 1)


class TestWhatsAppSendRetry(unittest.TestCase):
    """Tests bounded retries and exponential backoff for WhatsApp Graph API calls."""

    def test_transient_error_classification(self):
        """Verify 429 and 5xx are transient, 400 and 401 are permanent."""
        err_429 = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
        err_500 = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)
        err_503 = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)
        err_400 = urllib.error.HTTPError("url", 400, "Bad Request", {}, None)
        err_401 = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        err_403 = urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

        self.assertTrue(is_transient_whatsapp_error(err_429))
        self.assertTrue(is_transient_whatsapp_error(err_500))
        self.assertTrue(is_transient_whatsapp_error(err_503))
        self.assertTrue(is_transient_whatsapp_error(urllib.error.URLError("Connection refused")))
        self.assertTrue(is_transient_whatsapp_error(TimeoutError("Timed out")))

        self.assertFalse(is_transient_whatsapp_error(err_400))
        self.assertFalse(is_transient_whatsapp_error(err_401))
        self.assertFalse(is_transient_whatsapp_error(err_403))
        self.assertFalse(is_transient_whatsapp_error(WhatsAppValidationError("Invalid input")))

    @patch("urllib.request.urlopen")
    def test_send_text_retries_on_429_and_succeeds(self, mock_urlopen):
        """HTTP 429 transient rate limit retries and returns success when next attempt works."""
        # 1st call fails with 429, 2nd call succeeds
        err_429 = urllib.error.HTTPError("url", 429, "Rate limit", {}, io.BytesIO(b"{}"))
        mock_success_resp = MagicMock()
        mock_success_resp.__enter__.return_value.read.return_value = json.dumps({"messages": [{"id": "wamid.123"}]}).encode("utf-8")
        mock_urlopen.side_effect = [err_429, mock_success_resp]

        service = WhatsAppService(access_token="fake_token", phone_number_id="12345")
        # Use backoff_base=0.0 to execute instantly in test
        res = service.send_text("919876543210", "Hello", backoff_base=0.0)

        self.assertEqual(res["messages"][0]["id"], "wamid.123")
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("urllib.request.urlopen")
    def test_send_text_does_not_retry_permanent_400(self, mock_urlopen):
        """Permanent HTTP 400 Bad Request fails immediately without retry."""
        err_400 = urllib.error.HTTPError("url", 400, "Bad Request", {}, io.BytesIO(b"Invalid phone"))
        mock_urlopen.side_effect = err_400

        service = WhatsAppService(access_token="fake_token", phone_number_id="12345")
        with self.assertRaises(WhatsAppUnavailableError) as ctx:
            service.send_text("919876543210", "Hello", backoff_base=0.0)

        self.assertIn("400", str(ctx.exception))
        # Must only have been called ONCE; no retry on 400
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("urllib.request.urlopen")
    def test_send_text_exhausts_retries_on_500(self, mock_urlopen):
        """Transient HTTP 500 error retries up to max_retries then raises exception."""
        err_500 = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, io.BytesIO(b"Server crash"))
        mock_urlopen.side_effect = err_500

        service = WhatsAppService(access_token="fake_token", phone_number_id="12345")
        with self.assertRaises(WhatsAppUnavailableError) as ctx:
            # 2 retries = 3 total attempts
            service.send_text("919876543210", "Hello", max_retries=2, backoff_base=0.0)

        self.assertIn("500", str(ctx.exception))
        self.assertEqual(mock_urlopen.call_count, 3)


class TestConfigValidation(unittest.TestCase):
    """Tests the configuration validation module."""

    def test_whatsapp_config_validation(self):
        """Tests WhatsApp config validator with missing vs present env vars."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigValidationError) as ctx:
                validate_whatsapp_config(require_send=True)
            self.assertIn("WHATSAPP_TOKEN", str(ctx.exception))
            self.assertIn("WHATSAPP_PHONE_NUMBER_ID", str(ctx.exception))

        with patch.dict(os.environ, {
            "WHATSAPP_TOKEN": "tok_123",
            "WHATSAPP_PHONE_NUMBER_ID": "pn_456",
            "WHATSAPP_VERIFY_TOKEN": "ver_789",
        }, clear=True):
            cfg = validate_whatsapp_config(require_send=True, require_verify=True)
            self.assertEqual(cfg["WHATSAPP_TOKEN"], "tok_123")
            self.assertEqual(cfg["WHATSAPP_PHONE_NUMBER_ID"], "pn_456")
            self.assertEqual(cfg["WHATSAPP_VERIFY_TOKEN"], "ver_789")

    def test_dynamodb_config_defaults(self):
        """DynamoDB config provides standard defaults when unset."""
        with patch.dict(os.environ, {}, clear=True):
            cfg = validate_dynamodb_config()
            self.assertEqual(cfg["CUSTOMERS_TABLE"], "Customers")
            self.assertEqual(cfg["TRANSACTIONS_TABLE"], "Transactions")
            self.assertEqual(cfg["AWS_REGION"], "us-east-1")

    def test_transcribe_config_validation(self):
        """Transcribe config requires TRANSCRIBE_S3_BUCKET when enabled."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigValidationError) as ctx:
                validate_transcribe_config(require_bucket=True)
            self.assertIn("TRANSCRIBE_S3_BUCKET", str(ctx.exception))

    def test_bedrock_config_validation(self):
        """Bedrock config requires BEDROCK_MODEL_ID when enabled."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigValidationError) as ctx:
                validate_bedrock_config(require_model_id=True)
            self.assertIn("BEDROCK_MODEL_ID", str(ctx.exception))

    def test_selective_environment_validation(self):
        """Validating selective features does not raise errors for unconfigured unrelated features."""
        with patch.dict(os.environ, {"BEDROCK_MODEL_ID": "anthropic.claude-3-haiku"}, clear=True):
            # Only validate bedrock and dynamodb
            res = validate_environment(["bedrock", "dynamodb"])
            self.assertIn("bedrock", res)
            self.assertIn("dynamodb", res)
            self.assertNotIn("whatsapp_send", res)


class TestAWSThrottlingHandling(unittest.TestCase):
    """Tests bounded exponential backoff on AWS Throttling exceptions."""

    def test_aws_transient_error_detection(self):
        """Correctly identifies Throttling and ProvisionedThroughputExceeded."""
        from botocore.exceptions import ClientError

        throttle_err = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        validation_err = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Invalid payload"}},
            "InvokeModel",
        )

        self.assertTrue(is_aws_transient_error(throttle_err))
        self.assertFalse(is_aws_transient_error(validation_err))

    def test_bedrock_extract_retries_on_throttling(self):
        """Bedrock extract_transaction retries when throttled, then parses result."""
        from botocore.exceptions import ClientError

        throttle_err = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )

        mock_payload = {
            "content": [{"type": "text", "text": '{"customerName": "Deepak", "type": "CREDIT", "amount": 100, "description": "milk"}'}]
        }
        success_resp = {"body": io.BytesIO(json.dumps(mock_payload).encode("utf-8"))}

        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = [throttle_err, success_resp]

        service = BedrockService(client=mock_client)
        # Patch sleep to avoid waiting in tests
        with patch("time.sleep"):
            res = service.extract_transaction("Deepak took milk for 100 on credit")

        self.assertEqual(res["customerName"], "Deepak")
        self.assertEqual(res["amount"], 100)
        self.assertEqual(mock_client.invoke_model.call_count, 2)

    def test_bedrock_generate_reply_fallback_on_persistent_throttle(self):
        """Bedrock generate_reply falls back to deterministic template when throttling persists."""
        from botocore.exceptions import ClientError

        throttle_err = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = throttle_err

        service = BedrockService(client=mock_client)
        with patch("time.sleep"):
            reply = service.generate_reply(
                {"customerName": "Ramesh", "type": "CREDIT", "amount": 500},
                balance=Decimal("1200"),
                original_text="Ramesh credit 500",
                language_code="hi-IN",
            )

        self.assertIn("Ramesh", reply)
        self.assertIn("500", reply)
        self.assertIn("1200", reply)
        # Retried twice before falling back
        self.assertEqual(mock_client.invoke_model.call_count, 3)


if __name__ == "__main__":
    unittest.main()
