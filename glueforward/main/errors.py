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
