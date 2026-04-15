"""Overload detection for identifying server-side overload conditions."""

from http import HTTPStatus
from typing import Set

from qreward.globals import (
    LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING,
    OVERLOAD_EXCEPTIONS,
    OVERLOAD_KEYWORDS,
    SYSTEM_OVERLOAD_INDICATORS,
)


MAX_EXCEPTION_CHAIN_DEPTH = 50


class OverloadChecker:
    """Checker for detecting server-side overload conditions from exceptions."""

    @staticmethod
    def check(exception: BaseException) -> bool:
        """Check if exception indicates server overload.

        Iteratively walks the exception chain (via __cause__ and __context__)
        up to MAX_EXCEPTION_CHAIN_DEPTH levels to detect overload signals.

        Args:
            exception: Exception to check

        Returns:
            True if server is overloaded
        """
        pending = [exception]
        visited: Set[int] = set()
        depth = 0

        while pending and depth < MAX_EXCEPTION_CHAIN_DEPTH:
            current = pending.pop(0)
            current_id = id(current)

            if current_id in visited:
                continue
            visited.add(current_id)
            depth += 1

            if OverloadChecker._check_single(current):
                return True

            for attr_name in ("__cause__", "__context__"):
                chained = getattr(current, attr_name, None)
                if chained is not None:
                    pending.append(chained)

        return False

    @staticmethod
    def _check_single(exception: BaseException) -> bool:
        """Check a single exception (without following chains) for overload signals.

        Args:
            exception: Exception to check

        Returns:
            True if this specific exception indicates server overload
        """
        # 1. HTTP status code check
        if hasattr(exception, "status_code"):
            status_code = exception.status_code
            if status_code in (
                HTTPStatus.SERVICE_UNAVAILABLE.value,
                HTTPStatus.TOO_MANY_REQUESTS.value,
                HTTPStatus.BAD_GATEWAY.value,
                HTTPStatus.GATEWAY_TIMEOUT.value,
            ):
                return True

        # 2. Exception type check (full module path)
        exception_type_full = (
            f"{type(exception).__module__}.{type(exception).__name__}"
        )
        exception_type_name = type(exception).__name__
        if (
            exception_type_full in OVERLOAD_EXCEPTIONS
            or exception_type_name in OVERLOAD_EXCEPTIONS
        ):
            return True

        # 3. Library-specific exception handling
        for lib_name, exceptions in LIBRARY_OVERLOAD_EXCEPTIONS_MAPPING.items():
            if lib_name in exception_type_full and any(
                exc in exception_type_name for exc in exceptions
            ):
                return True

        # 4. Exception message content check
        error_message = str(exception).lower()
        for keyword in OVERLOAD_KEYWORDS:
            if keyword in error_message:
                return True

        # 5. System-level check
        for indicator in SYSTEM_OVERLOAD_INDICATORS:
            if indicator in error_message:
                return True

        # 6. Check exception args
        if hasattr(exception, "args") and exception.args:
            if any(
                isinstance(arg, str)
                and any(keyword in arg.lower() for keyword in OVERLOAD_KEYWORDS)
                for arg in exception.args
            ):
                return True

        return False
