"""
Ledgerly - DynamoDB Data Layer & Deterministic Ledger Service
Handles Shops, Customers, Transactions and exact balance arithmetic.
"""

import os
import uuid
import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

try:
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
    from botocore.exceptions import (
        BotoCoreError,
        ClientError,
        NoCredentialsError,
        PartialCredentialsError,
        EndpointConnectionError,
    )
except ImportError:
    boto3 = None
    Key = None
    Attr = None
    BotoCoreError = ClientError = NoCredentialsError = PartialCredentialsError = EndpointConnectionError = Exception


class DynamoDBUnavailableError(Exception):
    """Raised when DynamoDB is not reachable, tables are missing, or credentials are unconfigured."""
    pass


class LedgerValidationError(Exception):
    """Raised when input validation for ledger operations fails."""
    pass


def _to_decimal(val: Union[int, float, str, Decimal]) -> Decimal:
    """Safely converts numeric value to Decimal for DynamoDB."""
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def _to_serializable(item: Any) -> Any:
    """Converts DynamoDB Decimal objects to int/float for JSON serialization."""
    if isinstance(item, list):
        return [_to_serializable(x) for x in item]
    if isinstance(item, dict):
        return {k: _to_serializable(v) for k, v in item.items()}
    if isinstance(item, Decimal):
        return int(item) if item % 1 == 0 else float(item)
    return item


class LedgerService:
    def __init__(
        self,
        customers_table_name: Optional[str] = None,
        transactions_table_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        self.customers_table_name = (
            customers_table_name
            or os.environ.get("CUSTOMERS_TABLE", "Customers")
        )
        self.transactions_table_name = (
            transactions_table_name
            or os.environ.get("TRANSACTIONS_TABLE", "Transactions")
        )
        self.endpoint_url = endpoint_url or os.environ.get("DYNAMODB_ENDPOINT_URL")
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        self._dynamodb = None

    def _get_resource(self):
        if boto3 is None:
            raise DynamoDBUnavailableError(
                "boto3 library is not available in the current environment."
            )

        if self._dynamodb is None:
            try:
                if self.endpoint_url:
                    self._dynamodb = boto3.resource(
                        "dynamodb",
                        region_name=self.region_name,
                        endpoint_url=self.endpoint_url,
                    )
                else:
                    self._dynamodb = boto3.resource(
                        "dynamodb",
                        region_name=self.region_name,
                    )
            except (NoCredentialsError, PartialCredentialsError) as e:
                raise DynamoDBUnavailableError(
                    f"AWS credentials not configured. Error: {str(e)}"
                )
            except Exception as e:
                raise DynamoDBUnavailableError(
                    f"Unable to initialize DynamoDB client: {str(e)}"
                )
        return self._dynamodb

    def _get_table(self, table_name: str):
        try:
            dynamo = self._get_resource()
            table = dynamo.Table(table_name)
            return table
        except (NoCredentialsError, PartialCredentialsError) as e:
            raise DynamoDBUnavailableError(
                f"AWS credentials not configured. Error: {str(e)}"
            )
        except Exception as e:
            raise DynamoDBUnavailableError(
                f"Failed to access table {table_name}: {str(e)}"
            )

    def _wrap_db_call(self, func, *args, **kwargs):
        """Executes a DynamoDB call with error-wrapping for graceful unconfigured/offline handling."""
        try:
            return func(*args, **kwargs)
        except (NoCredentialsError, PartialCredentialsError) as e:
            raise DynamoDBUnavailableError(
                f"AWS credentials not configured for DynamoDB: {str(e)}"
            )
        except EndpointConnectionError as e:
            raise DynamoDBUnavailableError(
                f"Could not connect to DynamoDB endpoint: {str(e)}"
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            raise DynamoDBUnavailableError(
                f"DynamoDB ClientError [{error_code}]: {error_msg}"
            )
        except BotoCoreError as e:
            raise DynamoDBUnavailableError(f"BotoCoreError: {str(e)}")

    # -------------------------------------------------------------------------
    # 1. create_customer()
    # -------------------------------------------------------------------------
    def create_customer(
        self,
        shop_id: str,
        name: str,
        phone: str,
        customer_id: Optional[str] = None,
        preferred_language: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new customer under a specific shop. Supports multilingual preferredLanguage (23 Indian langs)."""
        if not shop_id or not shop_id.strip():
            raise LedgerValidationError("shopId must not be empty")
        if not name or not name.strip():
            raise LedgerValidationError("name must not be empty")
        if not phone or not phone.strip():
            raise LedgerValidationError("phone must not be empty")

        cid = customer_id.strip() if customer_id and customer_id.strip() else f"cust_{uuid.uuid4().hex[:12]}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        lang = (preferred_language or language or "").strip() if (preferred_language or language) else ""
        # Normalize: short code or full
        if lang:
            lang = lang.strip()
        else:
            lang = None

        customer_item = {
            "customerId": cid,
            "shopId": shop_id.strip(),
            "name": name.strip(),
            "phone": phone.strip(),
            "balance": Decimal("0"),
            "createdAt": created_at,
        }
        if lang:
            customer_item["preferredLanguage"] = lang
            customer_item["language"] = lang

        table = self._get_table(self.customers_table_name)
        self._wrap_db_call(table.put_item, Item=customer_item)

        return _to_serializable(customer_item)

    # -------------------------------------------------------------------------
    # 2. get_customer()
    # -------------------------------------------------------------------------
    def get_customer(self, customer_id: str, shop_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a single customer by customerId."""
        if not customer_id or not customer_id.strip():
            raise LedgerValidationError("customerId must not be empty")

        table = self._get_table(self.customers_table_name)
        response = self._wrap_db_call(
            table.get_item, Key={"customerId": customer_id.strip()}
        )
        item = response.get("Item")
        if not item:
            return None

        if shop_id and item.get("shopId") != shop_id.strip():
            return None

        return _to_serializable(item)

    # -------------------------------------------------------------------------
    # 3. list_customers()
    # -------------------------------------------------------------------------
    def list_customers(self, shop_id: str) -> List[Dict[str, Any]]:
        """Lists all customers belonging to a shop."""
        if not shop_id or not shop_id.strip():
            raise LedgerValidationError("shopId must not be empty")

        table = self._get_table(self.customers_table_name)
        scan_kwargs = {}
        if Attr is not None:
            scan_kwargs["FilterExpression"] = Attr("shopId").eq(shop_id.strip())
        response = self._wrap_db_call(table.scan, **scan_kwargs)
        items = response.get("Items", [])
        return _to_serializable(items)

    # -------------------------------------------------------------------------
    # 4. get_customer_transactions()
    # -------------------------------------------------------------------------
    def get_customer_transactions(
        self, customer_id: str, shop_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves all transaction records for a given customer."""
        if not customer_id or not customer_id.strip():
            raise LedgerValidationError("customerId must not be empty")

        table = self._get_table(self.transactions_table_name)
        scan_kwargs = {}
        if Attr is not None:
            filter_expr = Attr("customerId").eq(customer_id.strip())
            if shop_id and shop_id.strip():
                filter_expr = filter_expr & Attr("shopId").eq(shop_id.strip())
            scan_kwargs["FilterExpression"] = filter_expr

        response = self._wrap_db_call(table.scan, **scan_kwargs)
        items = response.get("Items", [])
        items.sort(key=lambda x: str(x.get("createdAt", "")), reverse=True)
        return _to_serializable(items)

    # -------------------------------------------------------------------------
    # 4b. get_transaction() - Point lookup by transactionId primary key
    # -------------------------------------------------------------------------
    def get_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single transaction by transactionId primary key."""
        if not transaction_id or not str(transaction_id).strip():
            return None
        try:
            table = self._get_table(self.transactions_table_name)
            response = self._wrap_db_call(
                table.get_item, Key={"transactionId": str(transaction_id).strip()}
            )
            item = response.get("Item")
            if not item:
                return None
            return _to_serializable(item)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # 5. calculate_customer_balance()
    # -------------------------------------------------------------------------
    def calculate_customer_balance(
        self, customer_id: str, shop_id: Optional[str] = None
    ) -> Decimal:
        """
        DETERMINISTIC BALANCE CALCULATION RULE:
        balance = total CREDIT - total PAYMENT
        
        Calculated directly from stored transaction ledger entries.
        Never calculated by an AI model.
        """
        transactions = self.get_customer_transactions(customer_id, shop_id)
        total_credit = Decimal("0")
        total_payment = Decimal("0")

        for tx in transactions:
            tx_type = tx.get("type", "").upper()
            amt = _to_decimal(tx.get("amount", 0))
            if tx_type == "CREDIT":
                total_credit += amt
            elif tx_type == "PAYMENT":
                total_payment += amt

        balance = total_credit - total_payment
        return balance

    # -------------------------------------------------------------------------
    # 6. add_transaction()
    # -------------------------------------------------------------------------
    def update_customer_language(self, customer_id: str, language: str) -> None:
        """Updates customer's preferredLanguage (best-effort, for multilingual tracking)."""
        if not customer_id or not language:
            return
        try:
            table = self._get_table(self.customers_table_name)
            self._wrap_db_call(
                table.update_item,
                Key={"customerId": customer_id.strip()},
                UpdateExpression="SET preferredLanguage = :lang, #lang = :lang",
                ExpressionAttributeNames={"#lang": "language"},
                ExpressionAttributeValues={":lang": language.strip()},
            )
        except Exception:
            # Fallback without alias if #lang not needed
            try:
                table = self._get_table(self.customers_table_name)
                self._wrap_db_call(
                    table.update_item,
                    Key={"customerId": customer_id.strip()},
                    UpdateExpression="SET preferredLanguage = :lang",
                    ExpressionAttributeValues={":lang": language.strip()},
                )
            except Exception:
                pass

    def add_transaction(
        self,
        shop_id: str,
        customer_id: str,
        tx_type: str,
        amount: Union[int, float, str, Decimal],
        description: str = "",
        due_date: Optional[str] = None,
        transaction_id: Optional[str] = None,
        language: Optional[str] = None,
        transcript_language: Optional[str] = None,
        detected_language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Records a transaction (CREDIT or PAYMENT) and updates customer balance deterministically.
        Supports multilingual: stores language of voice/text (23 Indian langs).
        """
        if not shop_id or not shop_id.strip():
            raise LedgerValidationError("shopId must not be empty")
        if not customer_id or not customer_id.strip():
            raise LedgerValidationError("customerId must not be empty")

        clean_type = tx_type.strip().upper() if tx_type else ""
        if clean_type not in ("CREDIT", "PAYMENT"):
            raise LedgerValidationError("Transaction type must be CREDIT or PAYMENT")

        try:
            dec_amount = _to_decimal(amount)
        except Exception:
            raise LedgerValidationError("amount must be a valid numeric value")

        if dec_amount <= Decimal("0"):
            raise LedgerValidationError("amount must be greater than zero")

        tx_id = (
            transaction_id.strip()
            if transaction_id and transaction_id.strip()
            else f"tx_{uuid.uuid4().hex[:12]}"
        )

        # Idempotency check: if transaction_id was supplied and already exists, return existing record
        if transaction_id and transaction_id.strip():
            existing = self.get_transaction(tx_id)
            if existing:
                updated_balance = self.calculate_customer_balance(customer_id.strip(), shop_id.strip())
                existing_res = dict(existing)
                existing_res["updatedCustomerBalance"] = (
                    int(updated_balance) if updated_balance % 1 == 0 else float(updated_balance)
                )
                existing_res["is_duplicate"] = True
                return existing_res

        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Resolve language (prefer explicit language > transcript_language > detected_language)
        lang_to_store = (language or transcript_language or detected_language or "").strip() if (language or transcript_language or detected_language) else ""
        if lang_to_store:
            lang_to_store = lang_to_store.strip()

        tx_item = {
            "transactionId": tx_id,
            "shopId": shop_id.strip(),
            "customerId": customer_id.strip(),
            "type": clean_type,
            "amount": dec_amount,
            "description": description.strip() if description else "",
            "createdAt": created_at,
        }
        if due_date and due_date.strip():
            tx_item["dueDate"] = due_date.strip()
        if lang_to_store:
            tx_item["language"] = lang_to_store
            tx_item["transcriptLanguage"] = lang_to_store
            tx_item["detected_language"] = lang_to_store

        # 1. Write the transaction record
        tx_table = self._get_table(self.transactions_table_name)
        self._wrap_db_call(tx_table.put_item, Item=tx_item)

        # 2. Deterministically calculate the new customer balance from ledger
        updated_balance = self.calculate_customer_balance(customer_id.strip(), shop_id.strip())

        # 3. Update the customer's balance field + language in Customers table
        cust_table = self._get_table(self.customers_table_name)
        try:
            if lang_to_store:
                self._wrap_db_call(
                    cust_table.update_item,
                    Key={"customerId": customer_id.strip()},
                    UpdateExpression="SET balance = :bal, preferredLanguage = :lang",
                    ExpressionAttributeValues={":bal": updated_balance, ":lang": lang_to_store},
                )
            else:
                self._wrap_db_call(
                    cust_table.update_item,
                    Key={"customerId": customer_id.strip()},
                    UpdateExpression="SET balance = :bal",
                    ExpressionAttributeValues={":bal": updated_balance},
                )
        except Exception:
            # Fallback balance only
            try:
                self._wrap_db_call(
                    cust_table.update_item,
                    Key={"customerId": customer_id.strip()},
                    UpdateExpression="SET balance = :bal",
                    ExpressionAttributeValues={":bal": updated_balance},
                )
            except Exception:
                pass

        result = _to_serializable(tx_item)
        result["updatedCustomerBalance"] = (
            int(updated_balance) if updated_balance % 1 == 0 else float(updated_balance)
        )
        # Expose language in result for API
        if lang_to_store:
            result["language"] = lang_to_store
            result["detected_language"] = lang_to_store
        return result
