class GlueforwardError(Exception):
    """Base class for exceptions in this module."""

    def __init__(self, *args: object, message: str) -> None:
        super().__init__(message, *args)


class RetryableGlueforwardError(GlueforwardError):
    """Exception raised when a retryable error occurs"""

    __retry_immediately: bool

    def __init__(
        self,
        *args: object,
        message: str,
        retry_immediately: bool = False,
    ) -> None:
        super().__init__(*args, message=message)
        self.__retry_immediately = retry_immediately

    def get_retry_immediately(self) -> bool:
        return self.__retry_immediately
