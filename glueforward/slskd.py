import json
import logging
from typing import Optional
from io import StringIO
import httpx
from ruamel.yaml import YAML

from errors import GlueforwardError, RetryableGlueforwardError
from service_client import ServiceClient


class SlskdAuthFailed(GlueforwardError):
    """Exception raised when slskd authentication fails"""
    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to authenticate to slskd")


class SlskdSetPortFailed(RetryableGlueforwardError):
    """Exception raised when slskd port setting fails"""
    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to set slskd listening port")


class SlskdUnreachable(RetryableGlueforwardError):
    """Exception raised when slskd is unreachable"""
    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to reach slskd")


class SlskdReauthNeeded(RetryableGlueforwardError):
    """Exception raised when slskd needs reauthentication"""
    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            message="slskd needs reauthentication",
            retry_immediately=True,
        )


class SlskdIllegalPort(RetryableGlueforwardError):
    """Exception raised when an invalid port is provided"""
    def __init__(self, port: int, *args: object) -> None:
        super().__init__(
            *args,
            message=f"Invalid port {port} - must be between 1024 and 65535",
            retry_immediately=False,
        )


class SlskdClient(ServiceClient):
    __client: httpx.Client
    __credentials: dict[str, str]
    __token: Optional[str] = None
    __yaml: YAML

    def __init__(self, url: str, credentials: dict[str, str]):
        self.__credentials = credentials
        self.__client = httpx.Client(base_url=url)
        # Configure YAML parser
        self.__yaml = YAML()
        self.__yaml.preserve_quotes = True
        self.__yaml.indent(mapping=2, sequence=4, offset=2)
        logging.debug("slskd client created with base url %s", url)

    def get_is_authenticated(self) -> bool:
        return self.__token is not None

    def __request(self, method: str, url: str, **kwargs) -> Optional[httpx.Response]:
        """Send authenticated request to slskd API"""
        headers = kwargs.pop('headers', {})
        if self.get_is_authenticated():
            headers['Authorization'] = f"Bearer {self.__token}"

        try:
            response = self.__client.request(
                method=method,
                url=url,
                headers=headers,
                **kwargs
            )
            response.raise_for_status()
            return response
        except (httpx.ConnectError, httpx.ReadTimeout) as exception:
            raise SlskdUnreachable(self.__client.base_url) from exception
        except httpx.HTTPStatusError as exception:
            self._handle_request_exception(
                exception,
                SlskdAuthFailed,
                SlskdSetPortFailed
            )
            return None

    def authenticate(self) -> None:
        if self.get_is_authenticated():
            return
        logging.debug("Authenticating to slskd")
        response = self.__request(
            method="post",
            url="/api/v0/session",
            json=self.__credentials
        )
        self.__token = response.json().get('token')
        logging.debug("slskd client authenticated")

    def reset_authentication(self) -> None:
        self.__token = None
        logging.debug("slskd client authentication reset")

    def __get_current_config(self) -> dict:
        """Get current YAML config from slskd"""
        response = self.__request(method="get", url="/api/v0/options/yaml")
        try:
            response_json = response.json()
            if isinstance(response_json, str):
                return self.__yaml.load(response_json) or {}
            return self.__yaml.load(response_json.get('yaml', '')) or {}
        except ValueError:
            return self.__yaml.load(response.text) or {}

    def __update_config(self, config: dict) -> None:
        """Update slskd config with new YAML"""
        # Convert config to YAML string using StringIO stream
        # ruamel.yaml requires a stream to properly handle formatting/indentation
        stream = StringIO()
        self.__yaml.dump(config, stream)
        yaml_content = stream.getvalue()

        # The slskd API expects a JSON payload containing the YAML as a string property
        # json.dumps() ensures proper string escaping for the JSON payload
        self.__request(
            method="post",
            url="/api/v0/options/yaml",
            data=json.dumps(yaml_content),
            headers={"Content-Type": "application/json"}
        )

    def set_port(self, port: int) -> None:
        """Update the listening port in slskd config via API"""
        if not 1024 <= port <= 65535:
            raise SlskdIllegalPort(port)

        if not self.get_is_authenticated():
            self.authenticate()

        try:
            config = self.__get_current_config()
            if 'soulseek' not in config:
                config['soulseek'] = {}
            config['soulseek']['listen_port'] = port
            self.__update_config(config)
        except SlskdAuthFailed as exc:
            self.reset_authentication()
            raise SlskdReauthNeeded() from exc
        except httpx.HTTPStatusError as e:
            raise SlskdSetPortFailed("Failed to update port") from e
