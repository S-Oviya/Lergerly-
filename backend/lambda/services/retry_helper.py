"""
Ledgerly - Lightweight Retry Helper
Provides bounded exponential backoff with jitter and customizable transient error classification.
Suitable for AWS service throttling and WhatsApp Graph API transient errors within Lambda limits.
"""

import logging
import random
import time
from typing import Any, Callable, Optional, Sequence, Tuple, Type

logger = logging.getLogger(__name__)

# Standard AWS transient error codes
AWS_TRANSIENT_ERROR_CODES = {
    "ThrottlingException",
    "Throttling",
    "ProvisionedThroughputExceededException",
    "TooManyRequestsException",
    "RequestTimeout",
    "RequestTimeoutException",
    "InternalServerError",
    "ServiceUnavailable",
    "ServiceUnavailableException",
    "PriorRequestNotComplete",
}


def is_aws_transient_error(exc: Exception) -> bool:
    """
    Determines if a botocore / boto3 exception represents a transient failure or throttling.
    """
    exc_type_name = type(exc).__name__
    if exc_type_name in ("EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError"):
        return True

    # Check ClientError response structure
    if hasattr(exc, "response") and isinstance(exc.response, dict):
        error_info = exc.response.get("Error", {})
        code = error_info.get("Code", "")
        http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

        if code in AWS_TRANSIENT_ERROR_CODES:
            return True
        if http_status in (429, 500, 502, 503, 504):
            return True

    # Fallback to string matching in message
    msg = str(exc)
    for code in AWS_TRANSIENT_ERROR_CODES:
        if code in msg:
            return True
    return False


def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 2,
    base_delay: float = 0.2,
    max_delay: float = 2.0,
    jitter: bool = True,
    is_retryable_fn: Optional[Callable[[Exception], bool]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> Any:
    """
    Executes a callable with bounded exponential backoff on retryable errors.

    Args:
        func: The function to execute.
        *args: Positional arguments for func.
        max_retries: Maximum number of retry attempts (0 means try once, no retries).
        base_delay: Initial delay in seconds before first retry.
        max_delay: Cap on delay between retries.
        jitter: If True, adds randomized jitter (up to 25% of delay).
        is_retryable_fn: Callable accepting an Exception and returning bool.
        sleep_fn: Sleep function (injectable for instant unit tests).
        **kwargs: Keyword arguments for func.

    Returns:
        The return value of func(*args, **kwargs).

    Raises:
        The last encountered exception if all retries fail or if a non-retryable exception occurs.
    """
    retries = max(0, int(max_retries))
    attempt = 0

    while True:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            attempt += 1
            if attempt > retries:
                logger.warning(
                    f"Execution failed after {attempt} attempts: {exc}"
                )
                raise

            # Check if this exception is retryable
            if is_retryable_fn is not None and not is_retryable_fn(exc):
                logger.debug(
                    f"Encountered non-retryable exception: {exc}. Aborting retries."
                )
                raise

            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if jitter and delay > 0:
                delay += random.uniform(0, delay * 0.25)

            logger.info(
                f"Transient error on attempt {attempt}/{retries + 1} ({exc}). Retrying in {delay:.2f}s..."
            )
            sleep_fn(delay)
