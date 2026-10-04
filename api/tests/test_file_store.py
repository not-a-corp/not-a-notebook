"""The local FileStore, and the rules for a file's name."""

from __future__ import annotations

import hashlib
import io
import stat
from pathlib import Path

import pytest
from app.domain.errors import FileTooLarge, InvalidInput, UnsupportedFileType
from app.domain.files import check_file_name
from app.storage.local import LocalFileStore


@pytest.fixture
def store(tmp_path: Path) -> LocalFileStore:
    return LocalFileStore(str(tmp_path))


async def test_a_committed_file_is_where_its_key_says(store: LocalFileStore) -> None:
    content = b"region,sales\nN,1\n"

    staged = await store.stage(io.BytesIO(content), max_bytes=1024)
    await store.commit(staged, "user/conversation/sales.csv")

    path = store.root / "user" / "conversation" / "sales.csv"
    assert path.read_bytes() == content
    assert staged.size == len(content)
    assert staged.sha256 == hashlib.sha256(content).digest()


async def test_a_kernel_user_can_read_what_was_written(store: LocalFileStore) -> None:
    staged = await store.stage(io.BytesIO(b"x"), max_bytes=1024)
    await store.commit(staged, "user/conversation/a.csv")

    folder = store.root / "user" / "conversation"
    assert stat.S_IMODE((folder / "a.csv").stat().st_mode) == 0o644
    assert stat.S_IMODE(folder.stat().st_mode) == 0o755


async def test_nothing_is_visible_until_committed(store: LocalFileStore) -> None:
    staged = await store.stage(io.BytesIO(b"x"), max_bytes=1024)

    await store.discard(staged)

    assert list((store.root / ".staging").iterdir()) == []
    assert not (store.root / "user").exists()


async def test_a_file_over_the_limit_is_refused_and_left_nowhere(store: LocalFileStore) -> None:
    with pytest.raises(FileTooLarge):
        await store.stage(io.BytesIO(b"x" * 2048), max_bytes=1024)

    assert list((store.root / ".staging").iterdir()) == []


async def test_an_empty_file_is_refused(store: LocalFileStore) -> None:
    with pytest.raises(InvalidInput):
        await store.stage(io.BytesIO(b""), max_bytes=1024)


async def test_a_key_cannot_climb_out_of_the_root(store: LocalFileStore) -> None:
    staged = await store.stage(io.BytesIO(b"x"), max_bytes=1024)

    with pytest.raises(InvalidInput):
        await store.commit(staged, "../escaped.csv")


async def test_deleting_a_folder_takes_its_files(store: LocalFileStore) -> None:
    staged = await store.stage(io.BytesIO(b"x"), max_bytes=1024)
    await store.commit(staged, "user/conversation/a.csv")

    await store.delete_folder("user/conversation")

    assert not (store.root / "user" / "conversation").exists()


@pytest.mark.parametrize(
    "name",
    ["vendas 2025.xlsx", "Relatório final.csv", "data.PARQUET", "a.tsv", "b.xls", "c.xlsm"],
)
def test_ordinary_names_are_kept_as_given(name: str) -> None:
    assert check_file_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        None,
        "",
        " padded.csv",
        "../up.csv",
        "dir/file.csv",
        "dir\\file.csv",
        ".hidden.csv",
        "a\x00.csv",
    ],
)
def test_names_that_cannot_be_a_file_in_data_are_refused(name: str | None) -> None:
    with pytest.raises(InvalidInput):
        check_file_name(name)


@pytest.mark.parametrize("name", ["notes.txt", "data.json", "archive.zip", "noextension"])
def test_other_formats_are_unsupported(name: str) -> None:
    with pytest.raises(UnsupportedFileType):
        check_file_name(name)
