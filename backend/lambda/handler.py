"""
Ledgerly - AWS Lambda Ingestion, Bedrock Extraction & DynamoDB Data Layer Handler
Phase 3: Amazon Bedrock Natural-Language Extraction + REST Operations
"""

import os
import sys
import json
import re
import base64
from typing import Any, Dict, Tuple, Optional

# Ensure services directory is resolvable in Lambda and local test runs
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from services.ledger_service import (
    LedgerService,
    DynamoDBUnavailableError,
    LedgerValidationError,
)
from services.bedrock_service import (
    BedrockService,
    BedrockUnavailableError,
    BedrockExtractionError,
)

# Shared service instances
ledger_service = LedgerService()
bedrock_service = BedrockService()


def _build_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Constructs an API Gateway compatible HTTP response dictionary with CORS headers.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(payload),
    }


def _extract_and_validate_body(event: Dict[str, Any]) -> Tuple[bool, Any, int]:
    """
    Extracts and parses JSON body from the incoming API Gateway event.
    Returns: (is_valid, parsed_body_or_error_dict, status_code)
    """
    if not isinstance(event, dict):
        return False, {"success": False, "error": "Invalid event structure"}, 400

    raw_body = event.get("body")
    if raw_body is None:
        return False, {"success": False, "error": "Missing request body"}, 400

    if isinstance(raw_body, dict):
        parsed_body = raw_body
    elif isinstance(raw_body, str):
        if event.get("isBase64Encoded", False):
            try:
                raw_body = base64.b64decode(raw_body).decode("utf-8")
            except Exception:
                return False, {"success": False, "error": "Failed to decode base64 body"}, 400

        stripped_body = raw_body.strip()
        if not stripped_body:
            return False, {"success": False, "error": "Request body cannot be empty"}, 400

        try:
            parsed_body = json.loads(stripped_body)
        except (json.JSONDecodeError, TypeError):
            return False, {"success": False, "error": "Invalid JSON format"}, 400
    else:
        return False, {"success": False, "error": "Unsupported request body type"}, 400

    if not isinstance(parsed_body, dict):
        return False, {"success": False, "error": "Request body must be a JSON object"}, 400

    return True, parsed_body, 200


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Main AWS Lambda entry point supporting:
    - POST /message (or legacy POST without route): natural language note -> Bedrock extraction
    - POST /customers: create customer
    - GET /customers: list customers (requires ?shopId=...)
    - GET /customers/{customerId}: get single customer
    - POST /transactions: record transaction (CREDIT or PAYMENT)
    - GET /customers/{customerId}/transactions: list customer transactions
    """
    if not isinstance(event, dict):
        return _build_response(400, {"success": False, "error": "Invalid event payload"})

    # 1. CORS Preflight
    http_method = (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method", "POST")
    ).upper()

    if http_method == "OPTIONS":
        return _build_response(200, {"success": True, "status": "preflight_ok"})

    # Determine route path
    path = event.get("path") or event.get("rawPath") or ""
    path = path.rstrip("/") if path != "/" else "/"
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}

    try:
        # ---------------------------------------------------------------------
        # ROUTE: POST /customers
        # ---------------------------------------------------------------------
        if http_method == "POST" and path == "/customers":
            is_valid, body, status_code = _extract_and_validate_body(event)
            if not is_valid:
                return _build_response(status_code, body)

            # Validate required fields
            for f in ("shopId", "name", "phone"):
                if f not in body:
                    return _build_response(400, {"success": False, "error": f"Field '{f}' is required"})
                if not isinstance(body[f], str) or not body[f].strip():
                    return _build_response(400, {"success": False, "error": f"Field '{f}' cannot be empty"})

            customer = ledger_service.create_customer(
                shop_id=body["shopId"],
                name=body["name"],
                phone=body["phone"],
                customer_id=body.get("customerId"),
            )
            return _build_response(201, {"success": True, "customer": customer})

        # ---------------------------------------------------------------------
        # ROUTE: GET /customers
        # ---------------------------------------------------------------------
        if http_method == "GET" and path == "/customers":
            shop_id = query_params.get("shopId")
            if not shop_id or not shop_id.strip():
                return _build_response(400, {"success": False, "error": "Query parameter 'shopId' is required"})

            customers = ledger_service.list_customers(shop_id=shop_id.strip())
            return _build_response(200, {"success": True, "customers": customers, "count": len(customers)})

        # ---------------------------------------------------------------------
        # ROUTE: GET /customers/{customerId}/transactions
        # ---------------------------------------------------------------------
        tx_match = re.match(r"^/customers/([^/]+)/transactions$", path)
        if http_method == "GET" and (tx_match or (path_params.get("customerId") and path.endswith("/transactions"))):
            cid = path_params.get("customerId") or (tx_match.group(1) if tx_match else "")
            if not cid:
                return _build_response(400, {"success": False, "error": "customerId cannot be empty"})

            shop_id = query_params.get("shopId")
            transactions = ledger_service.get_customer_transactions(customer_id=cid, shop_id=shop_id)
            current_balance = ledger_service.calculate_customer_balance(customer_id=cid, shop_id=shop_id)
            return _build_response(
                200,
                {
                    "success": True,
                    "customerId": cid,
                    "balance": int(current_balance) if current_balance % 1 == 0 else float(current_balance),
                    "transactions": transactions,
                    "count": len(transactions),
                },
            )

        # ---------------------------------------------------------------------
        # ROUTE: GET /customers/{customerId}
        # ---------------------------------------------------------------------
        cust_match = re.match(r"^/customers/([^/]+)$", path)
        if http_method == "GET" and (cust_match or path_params.get("customerId")):
            cid = path_params.get("customerId") or (cust_match.group(1) if cust_match else "")
            if not cid:
                return _build_response(400, {"success": False, "error": "customerId cannot be empty"})

            shop_id = query_params.get("shopId")
            customer = ledger_service.get_customer(customer_id=cid, shop_id=shop_id)
            if not customer:
                return _build_response(404, {"success": False, "error": f"Customer '{cid}' not found"})
            return _build_response(200, {"success": True, "customer": customer})

        # ---------------------------------------------------------------------
        # ROUTE: POST /transactions
        # ---------------------------------------------------------------------
        if http_method == "POST" and path == "/transactions":
            is_valid, body, status_code = _extract_and_validate_body(event)
            if not is_valid:
                return _build_response(status_code, body)

            # Validate required fields
            for f in ("shopId", "customerId", "type", "amount"):
                if f not in body:
                    return _build_response(400, {"success": False, "error": f"Field '{f}' is required"})

            for str_f in ("shopId", "customerId", "type"):
                if not isinstance(body[str_f], str) or not body[str_f].strip():
                    return _build_response(400, {"success": False, "error": f"Field '{str_f}' cannot be empty"})

            # Validate transaction type
            tx_type = body["type"].strip().upper()
            if tx_type not in ("CREDIT", "PAYMENT"):
                return _build_response(
                    400,
                    {"success": False, "error": "Transaction type must be CREDIT or PAYMENT"},
                )

            # Validate amount
            try:
                amt = float(body["amount"])
            except (ValueError, TypeError):
                return _build_response(400, {"success": False, "error": "amount must be a numeric value"})

            if amt <= 0:
                return _build_response(400, {"success": False, "error": "amount must be greater than zero"})

            transaction = ledger_service.add_transaction(
                shop_id=body["shopId"],
                customer_id=body["customerId"],
                tx_type=tx_type,
                amount=amt,
                description=body.get("description", ""),
                due_date=body.get("dueDate"),
                transaction_id=body.get("transactionId"),
            )
            return _build_response(201, {"success": True, "transaction": transaction})

        # ---------------------------------------------------------------------
        # ROUTE: POST /message (or fallback message ingestion)
        # Invokes Amazon Bedrock for transaction entity extraction
        # ---------------------------------------------------------------------
        if http_method == "POST" and (not path or path in ("/", "/message")):
            is_valid, body, status_code = _extract_and_validate_body(event)
            if not is_valid:
                return _build_response(status_code, body)

            if "message" not in body:
                return _build_response(400, {"success": False, "error": "Field 'message' is required"})

            message_val = body["message"]
            if not isinstance(message_val, str):
                return _build_response(400, {"success": False, "error": "Field 'message' must be a string"})

            clean_message = message_val.strip()
            if not clean_message:
                return _build_response(400, {"success": False, "error": "Field 'message' cannot be empty"})

            # Extract structured transaction via Amazon Bedrock
            extracted_tx = bedrock_service.extract_transaction(clean_message)

            return _build_response(
                200,
                {
                    "success": True,
                    "message": clean_message,
                    "status": "received",
                    "extractedTransaction": extracted_tx,
                },
            )

        # ---------------------------------------------------------------------
        # Non-matching HTTP methods / routes
        # ---------------------------------------------------------------------
        if http_method not in ("GET", "POST"):
            return _build_response(
                405,
                {"success": False, "error": f"Method {http_method} not allowed."},
            )

        return _build_response(
            404,
            {"success": False, "error": f"Route not found: {http_method} {path}"},
        )

    except LedgerValidationError as e:
        return _build_response(400, {"success": False, "error": str(e)})

    except BedrockExtractionError as e:
        return _build_response(400, {"success": False, "error": f"Transaction extraction failed: {str(e)}"})

    except BedrockUnavailableError as e:
        return _build_response(
            503,
            {
                "success": False,
                "error": "Amazon Bedrock service is unavailable or not configured. Ensure AWS credentials and model access are configured.",
                "details": str(e),
            },
        )

    except DynamoDBUnavailableError as e:
        return _build_response(
            503,
            {
                "success": False,
                "error": "DynamoDB service is unavailable or not configured. Ensure AWS credentials, tables (CUSTOMERS_TABLE, TRANSACTIONS_TABLE), or DYNAMODB_ENDPOINT_URL are configured.",
                "details": str(e),
            },
        )

    except Exception as e:
        return _build_response(
            500,
            {"success": False, "error": "Internal server error", "details": str(e)},
        )
