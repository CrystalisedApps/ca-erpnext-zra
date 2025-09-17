from __future__ import annotations

from datetime import datetime
from typing import Callable, Literal, Optional, Union
from urllib import parse

import requests
import frappe
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document




class BaseEndpointsBuilder:
    """Abstract Endpoints Builder class"""

    def __init__(self) -> None:
        self.integration_request: str | Document | None = None
        self.error: str | Exception | None = None
        self._observers: list[ErrorObserver] = []
        self.doctype: str | Document | None = None
        self.document_name: str | None = None

    def attach(self, observer: ErrorObserver) -> None:
        self._observers.append(observer)

    def notify(self) -> None:
        for observer in self._observers:
            observer.update(self)


class ErrorObserver:
    """Error observer for failed integrations."""

    def update(self, notifier: BaseEndpointsBuilder) -> None:
        if notifier.error:
            update_integration_request(
                notifier.integration_request.name,
                status="Failed",
                output=None,
                error=str(notifier.error),
            )
         
            frappe.log_error(
                title="Fatal Error",
                message=str(notifier.error),
                reference_doctype=notifier.doctype,
                reference_name=notifier.document_name,
            )
            frappe.throw(
                """A Fatal Error was Encountered.
                Please check the Error Log for more details""",
                notifier.error,
                title="Fatal Error",
            )


class EndpointsBuilder(BaseEndpointsBuilder):
    """Handles communication with Crystal Smart Invoice API"""

    def __init__(self) -> None:
        super().__init__()
        self._url: str | None = None
        self._request_description: str | None = None
        self._payload: dict | None = None
        self._headers: dict | None = None
        self._settings: Document | None = None
        self._method: Literal["GET", "POST", "PATCH", "PUT"] | None = None
        self._success_callback: Callable | None = None
        self._error_callback: Callable | None = None

        self.attach(ErrorObserver())

    # ---------- Properties ---------- #
    @property
    def url(self): return self._url
    @url.setter
    def url(self, val: str): self._url = val

    @property
    def method(self): return self._method
    @method.setter
    def method(self, val: Literal["GET", "POST", "PATCH", "PUT"]): self._method = val

    @property
    def headers(self): return self._headers
    @headers.setter
    def headers(self, val: dict): self._headers = val

    @property
    def payload(self): return self._payload
    @payload.setter
    def payload(self, val: dict): self._payload = val

    @property
    def settings(self): return self._settings
    @settings.setter
    def settings(self, val: Document): self._settings = val

    @property
    def request_description(self): return self._request_description
    @request_description.setter
    def request_description(self, val: str): self._request_description = val

    @property
    def success_callback(self): return self._success_callback
    @success_callback.setter
    def success_callback(self, fn: Callable): self._success_callback = fn

    @property
    def error_callback(self): return self._error_callback
    @error_callback.setter
    def error_callback(self, fn: Callable): self._error_callback = fn

    # ---------- Helpers ---------- #
    # def refresh_token(self) -> str:
    #     """Refresh ZRA token and update headers."""
    #     try:
    #         settings = update_navari_settings_with_token(self._settings.name)
    #         if not settings:
    #             frappe.throw("Failed to refresh token", frappe.AuthenticationError)
    #         new_token = settings.access_token
    #         self._headers["Authorization"] = f"Bearer {new_token}"
    #         return new_token
    #     except requests.exceptions.RequestException as e:
    #         frappe.throw(f"Error refreshing token: {e}", frappe.AuthenticationError)

    # ---------- Main Remote Call ---------- #
    def make_remote_call(
        self,
        doctype: Document | str | None = None,
        document_name: str | None = None,
        retrying: bool = False,
    ) -> Optional[Union[dict, str, bytes]]:
        if not all([self._url, self._headers, self._method, self._success_callback]):
            frappe.throw("URL, headers, method, and success callback must be set.")

        if not self._settings or not getattr(self._settings, "is_active", 1):
            frappe.log_error(
                title="Inactive Crystal ZRA Smart Invoice Settings",
                message=f"Crystal ZRA Smart Invoice settings {self._settings.name if self._settings else ''} is inactive.",
                reference_doctype=doctype,
                reference_name=document_name,
            )
            return None

        self.doctype, self.document_name = doctype, document_name
        parsed_url = parse.urlparse(self._url)
        route_path = f"/{parsed_url.path.split('/')[-1]}"

        # Log request
        if not retrying:
            try:
                self.integration_request = create_request_log(
                    data=self._payload,
                    request_description=self._request_description,
                    is_remote_request=True,
                    service_name="Crystal VSDC",
                    request_headers=self._headers,
                    url=self._url,
                    reference_docname=document_name,
                    reference_doctype=doctype,
                )
            except frappe.LinkValidationError:
                self.integration_request = create_request_log(
                    data=self._payload,
                    request_description=self._request_description,
                    is_remote_request=True,
                    service_name="Crystal VSDC",
                    request_headers=self._headers,
                    url=self._url,
                    reference_doctype=doctype,
                )

        try:
            # Perform request
            if self._method == "POST":
                response = requests.post(self._url, json=self._payload, headers=self._headers)
            elif self._method == "GET":
                response = requests.get(self._url, params=self._payload, headers=self._headers)
            elif self._method == "PATCH":
                response = requests.patch(self._url, json=self._payload, headers=self._headers)
            elif self._method == "PUT":
                response = requests.put(self._url, json=self._payload, headers=self._headers)
            else:
                frappe.throw(f"Unsupported HTTP method: {self._method}")

            response_data = get_response_data(response)
            # update_last_request_date(datetime.now(), route_path)

            if response.status_code in {200, 201}:
                frappe.db.set_value("Integration Request", self.integration_request.name, "status", "Completed")

                self._success_callback(
                    response=response_data,
                    document_name=document_name,
                    doctype=doctype,
                    payload=self._payload,
                    settings_name=self._settings.name,
                )

                update_integration_request(
                    self.integration_request.name,
                    status="Completed",
                    output=str(response_data),
                )

            else:
                error_msg = extract_error(response_data)

                # if response.status_code == 401 and not retrying:
                #     self.refresh_token()
                #     return self.make_remote_call(doctype, document_name, retrying=True)

                update_integration_request(
                    self.integration_request.name,
                    status="Failed",
                    error=error_msg,
                )
                #on_zra_error(response_data, url=route_path, doctype=doctype, document_name=document_name)

                if self._error_callback:
                    self._error_callback(
                        response=response_data,
                        url=route_path,
                        doctype=doctype,
                        document_name=document_name,
                        payload=self._payload,
                        settings_name=self._settings.name,
                    )

            return response_data

        except Exception as e:
            self.error = e
            self.notify()
            return None


# ---------- Helpers ---------- #
def get_response_data(response: requests.Response) -> Optional[Union[dict, str, bytes]]:
    content_type = response.headers.get("Content-Type", "").lower()
    if "application/json" in content_type:
        return response.json()
    if any(t in content_type for t in ["text/plain", "text/html", "application/xml", "text/xml"]):
        return response.text.strip() if response.text.strip() else None
    if any(t in content_type for t in ["application/octet-stream", "application/pdf", "application/zip"]):
        return response.content
    return None


def extract_error(response_data: Union[dict, str, list]) -> str:
    if isinstance(response_data, str):
        return response_data
    if isinstance(response_data, list) and response_data:
        return str(response_data[0])
    if isinstance(response_data, dict):
        return str(response_data.get("message", response_data))
    return "Unknown error from Crystal VSDC API"


def update_integration_request(
    integration_request: str,
    status: Literal["Completed", "Failed"],
    output: str | None = None,
    error: str | None = None,
) -> None:
    fields = {"status": status}
    if error:
        fields["error"] = error[:5000]
    if output:
        fields["output"] = output[:5000]
    frappe.db.set_value("Integration Request", integration_request, fields, update_modified=False)
