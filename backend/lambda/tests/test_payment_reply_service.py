"""
Ledgerly - Unit and Integration Tests for Customer Payment-Reply Handling
Tests PaymentReplyService parser and handler integration.
"""

import os
import sys
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
from services.payment_reply_service import PaymentReplyService


class TestPaymentReplyService(unittest.TestCase):
    """Unit tests for deterministic PaymentReplyService parser."""

    def setUp(self):
        self.service = PaymentReplyService()

    def test_i_paid_rupees_symbol(self):
        """'I paid ₹500' -> PAYMENT, 500"""
        res = self.service.parse("I paid ₹500")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 500)
        self.assertEqual(res["source"], "whatsapp")

    def test_paid_number(self):
        """'paid 500' -> PAYMENT, 500"""
        res = self.service.parse("paid 500")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 500)

    def test_symbol_amount_paid(self):
        """'₹500 paid' -> PAYMENT, 500"""
        res = self.service.parse("₹500 paid")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 500)

    def test_payment_done_amount(self):
        """'payment done 500' -> PAYMENT, 500"""
        res = self.service.parse("payment done 500")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 500)

    def test_payment_made_amount(self):
        """'payment made 500' -> PAYMENT, 500"""
        res = self.service.parse("payment made 500")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 500)

    def test_i_have_paid_rs_comma(self):
        """'I have paid Rs 1,000' -> PAYMENT, 1000"""
        res = self.service.parse("I have paid Rs 1,000")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 1000)

    def test_ive_paid_rupees_symbol_comma(self):
        """'I\'ve paid ₹1,000' -> PAYMENT, 1000"""
        res = self.service.parse("I've paid ₹1,000")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 1000)

    def test_rs_dot_amount_paid(self):
        """'Rs. 750 paid' -> PAYMENT, 750"""
        res = self.service.parse("Rs. 750 paid")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 750)

    def test_payment_of_amount_done(self):
        """'payment of ₹500 done' -> PAYMENT, 500"""
        res = self.service.parse("payment of ₹500 done")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 500)

    def test_ambiguous_paid(self):
        """'paid' -> AMBIGUOUS"""
        res = self.service.parse("paid")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "AMBIGUOUS")
        self.assertIsNone(res["amount"])

    def test_ambiguous_i_paid(self):
        """'I paid' -> AMBIGUOUS"""
        res = self.service.parse("I paid")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "AMBIGUOUS")
        self.assertIsNone(res["amount"])

    def test_ambiguous_i_paid_everything(self):
        """'I paid everything' -> AMBIGUOUS"""
        res = self.service.parse("I paid everything")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "AMBIGUOUS")
        self.assertIsNone(res["amount"])

    def test_ambiguous_payment_done(self):
        """'payment done' -> AMBIGUOUS"""
        res = self.service.parse("payment done")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "AMBIGUOUS")
        self.assertIsNone(res["amount"])

    def test_ambiguous_settled(self):
        """'settled' -> AMBIGUOUS"""
        res = self.service.parse("settled")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "AMBIGUOUS")
        self.assertIsNone(res["amount"])

    def test_customer_name_supplied_separately(self):
        """Customer name supplied to parser is included in result"""
        res = self.service.parse("I paid ₹500", customer_name="Rahul Sharma")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "PAYMENT")
        self.assertEqual(res["amount"], 500)
        self.assertEqual(res["customerName"], "Rahul Sharma")

    def test_zero_amount_rejected(self):
        """'paid 0' or 'paid ₹0' -> AMBIGUOUS, amount rejected"""
        res = self.service.parse("paid 0")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "AMBIGUOUS")
        self.assertIsNone(res["amount"])

    def test_negative_amount_rejected(self):
        """'paid -500' -> AMBIGUOUS, amount rejected"""
        res = self.service.parse("paid -500")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "AMBIGUOUS")
        self.assertIsNone(res["amount"])

    def test_comma_formatted_amounts(self):
        """Comma formatted amounts: ₹10,000, Rs 1,500, Rs. 2,500"""
        res1 = self.service.parse("₹10,000 paid")
        self.assertEqual(res1["amount"], 10000)

        res2 = self.service.parse("paid Rs 1,500")
        self.assertEqual(res2["amount"], 1500)

        res3 = self.service.parse("payment made Rs. 2,500")
        self.assertEqual(res3["amount"], 2500)

    def test_normal_non_payment_message(self):
        """'Rahul bought rice for ₹500' -> None (not a payment reply)"""
        res = self.service.parse("Rahul bought rice for ₹500")
        self.assertIsNone(res)

        res_credit = self.service.parse("Ramesh took milk for 200 on credit")
        self.assertIsNone(res_credit)

    def test_multilingual_jama_bhugtan(self):
        """Indian language terms: '500 jama kiya', 'bhugtan 500'"""
        res1 = self.service.parse("500 jama kiya")
        self.assertIsNotNone(res1)
        self.assertEqual(res1["action"], "PAYMENT")
        self.assertEqual(res1["amount"], 500)

        res2 = self.service.parse("bhugtan 500 done")
        self.assertIsNotNone(res2)
        self.assertEqual(res2["action"], "PAYMENT")
        self.assertEqual(res2["amount"], 500)


class TestHandlerPaymentReplyIntegration(unittest.TestCase):
    """Integration tests for WhatsApp payment reply flow in Lambda handler."""

    def _make_whatsapp_event(self, text: str, from_number: str = "+919876543210", msg_id: str = "wamid_001"):
        """Helper to create a normalized WhatsApp webhook event."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "entry_001",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15550234567",
                                    "phone_number_id": "phone_id_001",
                                },
                                "messages": [
                                    {
                                        "from": from_number,
                                        "id": msg_id,
                                        "timestamp": "1710800000",
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        return {
            "httpMethod": "POST",
            "path": "/whatsapp/webhook",
            "body": json.dumps(payload),
        }

    @patch.object(handler.whatsapp_service, "send_text")
    @patch.object(handler.bedrock_service, "extract_transaction")
    @patch.object(handler.ledger_service, "add_transaction")
    @patch.object(handler.ledger_service, "list_customers")
    @patch.object(handler.ledger_service, "get_customer_transactions")
    def test_customer_payment_creates_payment_transaction(
        self, mock_get_txs, mock_list_custs, mock_add_tx, mock_extract, mock_send
    ):
        """
        'I paid ₹500' ->
        1. Recognized as PAYMENT of 500
        2. Calls LedgerService.add_transaction with tx_type='PAYMENT' and amount=500
        3. Normal Bedrock CREDIT flow is NOT executed
        """
        mock_list_custs.return_value = [
            {"customerId": "cust_123", "name": "Rahul", "phone": "+919876543210"}
        ]
        mock_get_txs.return_value = []
        mock_add_tx.return_value = {
            "transactionId": "wa_wamid_001",
            "shopId": "shop_test",
            "customerId": "cust_123",
            "type": "PAYMENT",
            "amount": Decimal("500"),
            "description": "Customer payment via WhatsApp",
            "updatedCustomerBalance": 1200,
        }
        mock_send.return_value = {"messages": [{"id": "wamid_reply"}]}

        event = self._make_whatsapp_event("I paid ₹500", from_number="+919876543210", msg_id="wamid_001")
        response = handler.lambda_handler(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertTrue(body["success"])
        self.assertEqual(body["count"], 1)

        result = body["results"][0]
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["paymentIntent"]["action"], "PAYMENT")
        self.assertEqual(result["paymentIntent"]["amount"], 500)
        self.assertEqual(result["balance"], 1200)

        # Verify add_transaction was called with PAYMENT and 500
        mock_add_tx.assert_called_once()
        _, kwargs = mock_add_tx.call_args
        self.assertEqual(kwargs["tx_type"], "PAYMENT")
        self.assertEqual(kwargs["amount"], 500)
        self.assertEqual(kwargs["customer_id"], "cust_123")
        self.assertEqual(kwargs["transaction_id"], "wa_wamid_001")

        # Verify normal CREDIT extraction was NOT called
        mock_extract.assert_not_called()

    @patch.object(handler.bedrock_service, "extract_transaction")
    @patch.object(handler.ledger_service, "add_transaction")
    @patch.object(handler.ledger_service, "list_customers")
    @patch.object(handler.ledger_service, "get_customer_transactions")
    def test_idempotency_duplicate_message_id_not_reinserted(
        self, mock_get_txs, mock_list_custs, mock_add_tx, mock_extract
    ):
        """
        Duplicate WhatsApp webhook message with same message_id does NOT re-insert into ledger.
        """
        mock_list_custs.return_value = [
            {"customerId": "cust_123", "name": "Rahul", "phone": "+919876543210"}
        ]
        # Existing transaction already has wa_wamid_001
        mock_get_txs.return_value = [
            {
                "transactionId": "wa_wamid_001",
                "customerId": "cust_123",
                "type": "PAYMENT",
                "amount": Decimal("500"),
            }
        ]

        with patch.object(handler.ledger_service, "calculate_customer_balance", return_value=Decimal("1200")):
            event = self._make_whatsapp_event("I paid ₹500", from_number="+919876543210", msg_id="wamid_001")
            response = handler.lambda_handler(event)

            self.assertEqual(response["statusCode"], 200)
            body = json.loads(response["body"])
            result = body["results"][0]
            self.assertTrue(result.get("duplicate"))
            self.assertEqual(result["balance"], 1200)

            # add_transaction must NOT be called again for duplicate message
            mock_add_tx.assert_not_called()
            mock_extract.assert_not_called()

    @patch.object(handler.whatsapp_service, "send_text")
    @patch.object(handler.bedrock_service, "extract_transaction")
    @patch.object(handler.ledger_service, "add_transaction")
    def test_ambiguous_payment_message_asks_clarification(
        self, mock_add_tx, mock_extract, mock_send
    ):
        """
        'payment done' -> AMBIGUOUS, returns ambiguous status and clarification,
        does not add transaction to ledger.
        """
        event = self._make_whatsapp_event("payment done", from_number="+919876543210", msg_id="wamid_002")
        response = handler.lambda_handler(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        result = body["results"][0]
        self.assertEqual(result["status"], "ambiguous")
        self.assertIn("specify", result["reply"].lower())

        # Neither ledger add_transaction nor Bedrock extraction should be executed
        mock_add_tx.assert_not_called()
        mock_extract.assert_not_called()

    @patch.object(handler.whatsapp_service, "send_text")
    @patch.object(handler.bedrock_service, "extract_transaction")
    @patch.object(handler.bedrock_service, "generate_reply")
    @patch.object(handler.ledger_service, "add_transaction")
    @patch.object(handler.ledger_service, "list_customers")
    @patch.object(handler.ledger_service, "create_customer")
    def test_normal_credit_flow_still_executed(
        self, mock_create_cust, mock_list_cust, mock_add_tx, mock_reply, mock_extract, mock_send
    ):
        """
        'Rahul bought rice for ₹500' -> normal credit pipeline executed.
        """
        mock_extract.return_value = {
            "customerName": "Rahul",
            "type": "CREDIT",
            "amount": 500,
            "description": "rice",
        }
        mock_list_cust.return_value = [
            {"customerId": "cust_123", "name": "Rahul", "phone": "+919876543210"}
        ]
        mock_add_tx.return_value = {
            "transactionId": "tx_normal_001",
            "shopId": "shop_test",
            "customerId": "cust_123",
            "type": "CREDIT",
            "amount": Decimal("500"),
            "updatedCustomerBalance": 500,
        }
        mock_reply.return_value = "Rahul ke liye 500 CREDIT record kiya. Balance: 500. ✅"

        event = self._make_whatsapp_event("Rahul bought rice for ₹500", from_number="+919876543210", msg_id="wamid_003")
        response = handler.lambda_handler(event)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        result = body["results"][0]
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["extractedTransaction"]["type"], "CREDIT")

        # Bedrock extraction WAS called for normal credit message
        mock_extract.assert_called_once()
        # add_transaction called with CREDIT
        mock_add_tx.assert_called_once()
        _, kwargs = mock_add_tx.call_args
        self.assertEqual(kwargs["tx_type"], "CREDIT")


if __name__ == "__main__":
    unittest.main()
