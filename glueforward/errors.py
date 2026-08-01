class RetryableError(Exception):
    """Exception raised when a retryable error occurs"""

    __retry_immediately: bool

    def __init__(
        self,
        *args: object,
        message: str,
        retry_immediately: bool = False,
    ) -> None:
        super().__init__(*args, message)
        self.__retry_immediately = retry_immediately

    def get_retry_immediately(self) -> bool:
        return self.__retry_immediately
