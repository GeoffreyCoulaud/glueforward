from abc import ABC, abstractmethod
from typing import NoReturn
import httpx

class ServiceClient(ABC):
    """Abstract base class for service clients that handle port configuration"""

    @abstractmethod
    def get_service_name(self) -> str:
        """Get the name of the service"""

    @abstractmethod
    def set_port(self, port: int) -> None:
        """Update the service's listening port

        Args:
            port: The port number to set (1024-65535)
        """

    def _handle_request_exception(
        self,
        exception: httpx.HTTPStatusError,
        auth_error_class: type,
        unreachable_error_class: type,
    ) -> NoReturn:
        """Shared exception handler for service client requests

        Args:
            exception: The HTTPStatusError that occurred
            auth_error_class: Exception class to raise for auth errors (401/403)
            unreachable_error_class: Exception class to raise for 5xx errors
        """
        if exception.response.status_code in (401, 403):
            raise auth_error_class(
                exception.response.status_code,
                exception.response.text
            ) from exception
        if exception.response.status_code // 100 == 5:
            raise unreachable_error_class(
                exception.response.status_code,
                exception.response.text
            ) from exception
        raise exception
