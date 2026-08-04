from enum import IntEnum


class ReturnCodes(IntEnum):
    """The exit codes glueforward stops on, part of the container's interface."""

    MISSING_ENVIRONMENT_VARIABLE = 1
    UNKNOWN_SERVICE_TYPE = 2
    UNRETRYABLE_EXCEPTION_IN_LIFECYCLE = 3
    INVALID_ENVIRONMENT_VARIABLE = 4


class RetryableError(Exception):
    """Exception raised when a retryable error occurs"""

    def __init__(
        self,
        *args: object,
        retry_immediately: bool = False,
    ) -> None:
        super().__init__(*args)
        self._retry_immediately = retry_immediately

    def get_retry_immediately(self) -> bool:
        return self._retry_immediately
