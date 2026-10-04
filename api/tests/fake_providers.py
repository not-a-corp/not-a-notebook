"""Google and GitHub as far as the OAuth flow can tell, answering from memory.

Every request is kept, so a test can check what was sent — the verifier, the
redirect URI — and not only what came back.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import httpx2


class FakeProviders:
    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []

        self.token_status = 200
        self.token_body: dict[str, Any] = {"access_token": "provider-token"}
        self.unreachable = False

        self.google_user: dict[str, Any] = {
            "sub": "google-123",
            "email": "rafael@example.com",
            "email_verified": True,
        }
        self.github_user: dict[str, Any] = {"id": 42, "login": "rafael"}
        self.github_emails: list[dict[str, Any]] = [
            {"email": "rafael@example.com", "primary": True, "verified": True},
        ]

    def client(self) -> httpx2.AsyncClient:
        transport = httpx2.MockTransport(self.handle)

        return httpx2.AsyncClient(transport=transport)

    def token_requests(self) -> list[dict[str, list[str]]]:
        forms = []

        for request in self.requests:
            if request.method == "POST":
                body = request.content.decode()
                forms.append(parse_qs(body))

        return forms

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)

        if self.unreachable:
            raise httpx2.ConnectError("the provider is down", request=request)

        routes = {
            ("oauth2.googleapis.com", "/token"): (self.token_status, self.token_body),
            ("github.com", "/login/oauth/access_token"): (self.token_status, self.token_body),
            ("openidconnect.googleapis.com", "/v1/userinfo"): (200, self.google_user),
            ("api.github.com", "/user"): (200, self.github_user),
            ("api.github.com", "/user/emails"): (200, self.github_emails),
        }

        key = (request.url.host, request.url.path)
        status, body = routes.get(key, (404, {"message": "Not Found"}))

        return httpx2.Response(status, json=body)
