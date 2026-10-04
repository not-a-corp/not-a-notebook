"""The few Docker Engine API calls the runtime makes, over the Unix socket.

Spoken directly with httpx2 rather than through an SDK: it is a dozen endpoints of
a versioned API, and one HTTP library in the project is better than two.

Every non-2xx answer raises DockerError with Docker's own message. The caller
decides what that means — starting a kernel turns it into SANDBOX_UNAVAILABLE.

**The socket is root on the host.** For self-host that is accepted and
documented; the hosted version goes through a socket proxy that allows only what
this file calls (decision 2).
"""

from __future__ import annotations

from typing import Any

import httpx2

# The version the calls below were written against. Pinning it means a newer
# daemon answers in the shape this code expects.
API_VERSION = "v1.47"

SOCKET = "/var/run/docker.sock"


class DockerError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"docker answered {status}: {message}")


class DockerEngine:
    def __init__(self, http: httpx2.AsyncClient) -> None:
        self.http = http

    @classmethod
    def over_socket(cls, socket: str = SOCKET) -> DockerEngine:
        transport = httpx2.AsyncHTTPTransport(uds=socket)
        # The host is ignored over a Unix socket; Docker only wants something there.
        http = httpx2.AsyncClient(transport=transport, base_url=f"http://docker/{API_VERSION}")

        return cls(http)

    async def close(self) -> None:
        await self.http.aclose()

    async def create_network(self, name: str, labels: dict[str, str]) -> str:
        # internal: no gateway, so nothing on this network reaches outside it —
        # not the internet, not the host.
        body = {
            "Name": name,
            "Internal": True,
            "Labels": labels,
        }
        created = await self.request("POST", "/networks/create", json=body)

        return str(created["Id"])

    async def connect_network(self, network: str, container: str) -> None:
        body = {"Container": container}

        await self.request("POST", f"/networks/{network}/connect", json=body)

    async def disconnect_network(self, network: str, container: str) -> None:
        body = {"Container": container, "Force": True}

        await self.request("POST", f"/networks/{network}/disconnect", json=body)

    async def remove_network(self, network: str) -> None:
        await self.request("DELETE", f"/networks/{network}")

    async def create_container(self, name: str, config: dict[str, Any]) -> str:
        params = {"name": name}
        created = await self.request("POST", "/containers/create", params=params, json=config)

        return str(created["Id"])

    async def start_container(self, container: str) -> None:
        await self.request("POST", f"/containers/{container}/start")

    async def inspect_container(self, container: str) -> dict[str, Any]:
        return await self.request("GET", f"/containers/{container}/json")

    async def remove_container(self, container: str) -> None:
        params = {"force": "true", "v": "true"}

        await self.request("DELETE", f"/containers/{container}", params=params)

    async def inspect_network(self, network: str) -> dict[str, Any]:
        return await self.request("GET", f"/networks/{network}")

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self.http.request(method, path, params=params, json=json)

        if response.status_code >= 400:
            message = response.text
            raise DockerError(response.status_code, message)

        # 204 No Content and the empty 200s of start and connect.
        if not response.content:
            return {}

        body: dict[str, Any] = response.json()
        return body
