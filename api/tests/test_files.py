"""POST and DELETE /conversations/{id}/files — and the run that profiles each upload.

Most tests swap in FakeKernels: they are about the route, and a real kernel's
start would only make them slow. The tests under "profiled for real" run the
whole path, in a real kernel, on real CSV, Excel and Parquet files.
"""

from __future__ import annotations

import io
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from app.config import get_settings
from app.main import app
from fastapi.testclient import TestClient
from tests.auth_helpers import ANA, RAFAEL, bearer, sign_up_and_in
from tests.conftest import Run
from tests.fake_kernels import CANNED_PROFILE, FakeKernels

CONVERSATIONS = "/api/v1/conversations"
CSV = b"region,sales\nN,10\nS,\nNE,7\n"


@pytest.fixture
def token(client: TestClient) -> str:
    return sign_up_and_in(client, RAFAEL)


@pytest.fixture
def conversation(client: TestClient, token: str) -> str:
    response = client.post(CONVERSATIONS, headers=bearer(token), json={})

    return str(response.json()["id"])


@pytest.fixture
def fake_kernels(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeKernels]:
    kernels = FakeKernels()
    monkeypatch.setattr(app.state, "kernels", kernels)
    yield kernels


def upload(
    client: TestClient,
    token: str,
    conversation: str,
    name: str = "sales.csv",
    content: bytes = CSV,
) -> Any:
    files = {"file": (name, io.BytesIO(content), "application/octet-stream")}

    return client.post(f"{CONVERSATIONS}/{conversation}/files", headers=bearer(token), files=files)


def settled(client: TestClient, token: str, conversation: str) -> dict[str, Any]:
    """The conversation once no run is in progress — every upload profiled."""
    deadline = time.monotonic() + 120

    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(
            f"{CONVERSATIONS}/{conversation}", headers=bearer(token)
        ).json()
        if body["active_run_id"] is None:
            return body

        time.sleep(0.5)

    raise AssertionError("the profiling run never finished")


def stored_path(sql: Run, file_id: str) -> Path:
    rows = sql(
        """
        SELECT f.storage_key
          FROM files f
         WHERE f.external_id = %(id)s
        """,
        {"id": file_id},
    )

    return Path(get_settings().files_root) / rows[0][0]


# ── the upload ───────────────────────────────────────────────────────────────


def test_an_upload_is_accepted_with_the_run_that_profiles_it(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels
) -> None:
    response = upload(client, token, conversation)

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"file", "run_id"}
    assert set(body["file"]) == {"id", "name", "bytes", "profile", "created_at"}
    assert body["file"]["name"] == "sales.csv"
    assert body["file"]["bytes"] == len(CSV)
    assert body["file"]["profile"] is None


def test_the_bytes_land_in_the_conversations_folder(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels, sql: Run
) -> None:
    file_id = upload(client, token, conversation).json()["file"]["id"]

    path = stored_path(sql, file_id)
    assert path.read_bytes() == CSV
    assert path.parent.name == conversation
    assert path.name == "sales.csv"


def test_the_profile_is_written_when_the_run_finishes(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels, sql: Run
) -> None:
    run_id = upload(client, token, conversation).json()["run_id"]

    body = settled(client, token, conversation)

    assert body["files"][0]["profile"] == CANNED_PROFILE
    rows = sql(
        """
        SELECT r.kind, r.status, r.finished_at IS NOT NULL
          FROM runs r
         WHERE r.external_id = %(id)s
        """,
        {"id": run_id},
    )
    assert rows == [("profile", "succeeded", True)]


def test_an_upload_counts_as_activity(
    client: TestClient, token: str, fake_kernels: FakeKernels
) -> None:
    older = client.post(CONVERSATIONS, headers=bearer(token), json={"title": "older"}).json()
    client.post(CONVERSATIONS, headers=bearer(token), json={"title": "newer"})

    upload(client, token, older["id"])

    listed = client.get(CONVERSATIONS, headers=bearer(token)).json()["data"]
    assert listed[0]["title"] == "older"


def test_the_same_name_twice_is_a_conflict(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels
) -> None:
    upload(client, token, conversation)
    settled(client, token, conversation)

    response = upload(client, token, conversation, content=b"other,content\n1,2\n")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FILE_ALREADY_EXISTS"


def test_a_refused_upload_leaves_the_first_file_untouched(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels, sql: Run
) -> None:
    file_id = upload(client, token, conversation).json()["file"]["id"]
    settled(client, token, conversation)

    upload(client, token, conversation, content=b"other,content\n1,2\n")

    assert stored_path(sql, file_id).read_bytes() == CSV


def test_an_upload_while_a_run_is_in_progress_is_busy(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels, sql: Run
) -> None:
    sql(
        """
        INSERT INTO runs AS r (conversation_id, kind)
        SELECT c.id, 'cell'
          FROM conversations c
         WHERE c.external_id = %(id)s
        """,
        {"id": conversation},
    )

    response = upload(client, token, conversation)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONVERSATION_BUSY"
    assert sql("SELECT f.id FROM files f") == []


@pytest.mark.parametrize("name", ["notes.txt", "data.json"])
def test_other_formats_are_unsupported(
    client: TestClient, token: str, conversation: str, name: str
) -> None:
    response = upload(client, token, conversation, name=name)

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.parametrize("name", ["../escape.csv", ".hidden.csv"])
def test_a_name_that_is_not_a_file_in_data_is_refused(
    client: TestClient, token: str, conversation: str, name: str
) -> None:
    response = upload(client, token, conversation, name=name)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_an_empty_file_is_refused(client: TestClient, token: str, conversation: str) -> None:
    response = upload(client, token, conversation, content=b"")

    assert response.status_code == 422


def test_a_file_over_the_limit_is_too_large(
    client: TestClient, token: str, conversation: str, monkeypatch: pytest.MonkeyPatch, sql: Run
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()

    response = upload(client, token, conversation, content=b"x," * (600 * 1024))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert sql("SELECT f.id FROM files f") == []


def test_a_request_without_a_file_is_a_validation_error(
    client: TestClient, token: str, conversation: str
) -> None:
    response = client.post(f"{CONVERSATIONS}/{conversation}/files", headers=bearer(token))

    assert response.status_code == 422


def test_someone_elses_conversation_is_not_found(
    client: TestClient, token: str, conversation: str
) -> None:
    ana = sign_up_and_in(client, ANA)

    response = upload(client, ana, conversation)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


# ── deleting ─────────────────────────────────────────────────────────────────


def test_deleting_a_file_removes_it_from_disk(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels, sql: Run
) -> None:
    file_id = upload(client, token, conversation).json()["file"]["id"]
    settled(client, token, conversation)
    path = stored_path(sql, file_id)

    response = client.delete(
        f"{CONVERSATIONS}/{conversation}/files/{file_id}", headers=bearer(token)
    )

    assert response.status_code == 204
    assert not path.exists()
    assert settled(client, token, conversation)["files"] == []


def test_deleting_an_unknown_file_is_not_found(
    client: TestClient, token: str, conversation: str
) -> None:
    response = client.delete(
        f"{CONVERSATIONS}/{conversation}/files/{uuid4()}", headers=bearer(token)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_deleting_while_a_run_is_in_progress_is_busy(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels, sql: Run
) -> None:
    file_id = upload(client, token, conversation).json()["file"]["id"]
    settled(client, token, conversation)
    sql(
        """
        INSERT INTO runs AS r (conversation_id, kind)
        SELECT c.id, 'cell'
          FROM conversations c
         WHERE c.external_id = %(id)s
        """,
        {"id": conversation},
    )

    response = client.delete(
        f"{CONVERSATIONS}/{conversation}/files/{file_id}", headers=bearer(token)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONVERSATION_BUSY"


def test_someone_elses_file_is_not_found(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels
) -> None:
    file_id = upload(client, token, conversation).json()["file"]["id"]
    settled(client, token, conversation)
    ana = sign_up_and_in(client, ANA)

    response = client.delete(f"{CONVERSATIONS}/{conversation}/files/{file_id}", headers=bearer(ana))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_deleting_the_conversation_removes_its_folder(
    client: TestClient, token: str, conversation: str, fake_kernels: FakeKernels, sql: Run
) -> None:
    file_id = upload(client, token, conversation).json()["file"]["id"]
    settled(client, token, conversation)
    folder = stored_path(sql, file_id).parent

    client.delete(f"{CONVERSATIONS}/{conversation}", headers=bearer(token))

    assert not folder.exists()
    assert fake_kernels.running() == set()


# ── abandoned runs ───────────────────────────────────────────────────────────


def test_runs_left_running_by_a_dead_process_are_closed_on_startup(
    migrated_database: str, monkeypatch: pytest.MonkeyPatch, sql: Run, client: TestClient
) -> None:
    token = sign_up_and_in(client, RAFAEL)
    conversation = client.post(CONVERSATIONS, headers=bearer(token), json={}).json()["id"]
    sql(
        """
        INSERT INTO runs AS r (conversation_id, kind)
        SELECT c.id, 'profile'
          FROM conversations c
         WHERE c.external_id = %(id)s
        """,
        {"id": conversation},
    )

    # A second start of the API, as after a crash.
    with TestClient(app):
        pass

    rows = sql("SELECT r.status, r.finished_at IS NOT NULL FROM runs r")
    assert rows == [("failed", True)]


# ── profiled for real ────────────────────────────────────────────────────────


def excel_with_two_sheets() -> bytes:
    workbook = openpyxl.Workbook()
    notes = workbook.active
    assert notes is not None
    notes.title = "Leia-me"
    notes.append(["Relatório de vendas, gerado em 2025"])

    sales = workbook.create_sheet("Vendas")
    sales.append(["região", "vendas"])
    sales.append(["Sudeste", 1840000])
    sales.append(["Nordeste", 512000])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def parquet_table() -> bytes:
    table = pa.table({"region": ["N", "S", None], "sales": [10.5, 3.0, 7.25]})

    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    return buffer.getvalue()


def test_a_csv_is_profiled_in_a_real_kernel(
    client: TestClient, token: str, conversation: str
) -> None:
    upload(client, token, conversation, name="sales.csv", content=CSV)

    body = settled(client, token, conversation)

    profile = body["files"][0]["profile"]
    assert profile["readable"] is True
    assert profile["format"] == "csv"
    table = profile["tables"][0]
    assert table["rows"] == 3
    assert [c["name"] for c in table["columns"]] == ["region", "sales"]
    assert table["columns"][1]["missing"] == 1

    # The kernel stays up for the conversation's next run.
    assert body["kernel"] == "running"


def test_an_excel_file_is_profiled_sheet_by_sheet(
    client: TestClient, token: str, conversation: str
) -> None:
    upload(client, token, conversation, name="vendas.xlsx", content=excel_with_two_sheets())

    profile = settled(client, token, conversation)["files"][0]["profile"]

    assert profile["format"] == "excel"
    assert profile["sheets"] == ["Leia-me", "Vendas"]
    sales = profile["tables"][1]
    assert sales["sheet"] == "Vendas"
    assert sales["rows"] == 2


def test_a_parquet_file_is_profiled(client: TestClient, token: str, conversation: str) -> None:
    upload(client, token, conversation, name="sales.parquet", content=parquet_table())

    profile = settled(client, token, conversation)["files"][0]["profile"]

    assert profile["format"] == "parquet"
    columns = profile["tables"][0]["columns"]
    assert columns[0]["missing"] == 1
    assert columns[1]["dtype"] == "float64"


def test_a_file_that_is_not_what_it_says_is_still_profiled(
    client: TestClient, token: str, conversation: str, sql: Run
) -> None:
    run_id = upload(client, token, conversation, name="broken.parquet", content=b"not parquet")
    run_id = run_id.json()["run_id"]

    profile = settled(client, token, conversation)["files"][0]["profile"]

    assert profile["readable"] is False
    assert profile["error"]
    status = sql("SELECT r.status FROM runs r WHERE r.external_id = %(id)s", {"id": run_id})
    assert status == [("succeeded",)]


def test_profiling_does_not_touch_the_users_execution_count(
    client: TestClient, token: str, conversation: str
) -> None:
    """The profile runs with store_history=False; the first cell the user runs
    must still be [1]. Checked from the kernel: its next count is 1."""
    upload(client, token, conversation)
    settled(client, token, conversation)

    kernels = app.state.kernels
    kernel = next(iter(kernels.kernels.values()))

    async def first_count() -> int | None:
        async def ignore(output: object) -> None:
            pass

        result = await kernel.execute("1", ignore)
        return result.execution_count

    count = client.portal.call(first_count)  # type: ignore[attr-defined]
    assert count == 1
