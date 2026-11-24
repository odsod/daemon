import hashlib

import pytest

from odsod_daemon.lib import download

pytestmark = pytest.mark.looptime(False)


def pins(url: str, files: dict[str, bytes]) -> list[download.Pin]:
    return [
        download.Pin(name, f"{url}/{name}", hashlib.sha256(data).hexdigest(), len(data))
        for name, data in files.items()
    ]


async def test_fetch_checks_hashes_and_skips_present_files(tmp_path, file_server):
    data = {"a.onnx": b"weights" * 1000, "vocab.txt": b"a\nb\n"}
    file_server.files.update(data)
    url = file_server.url
    assert await download.fetch(tmp_path, pins(url, data)) == ["a.onnx", "vocab.txt"]
    assert (tmp_path / "a.onnx").read_bytes() == data["a.onnx"]
    assert await download.fetch(tmp_path, pins(url, data)) == []
    assert sorted(file_server.gets) == ["a.onnx", "vocab.txt"]
    wrong = download.Pin("b.onnx", f"{url}/b.onnx", "0" * 64, 3)
    file_server.files["b.onnx"] = b"bad"
    with pytest.raises(download.DownloadError, match="SHA-256"):
        await download.fetch(tmp_path, [wrong])
    assert not list(tmp_path.glob("b.onnx*"))
    with pytest.raises(download.DownloadError):
        await download.fetch(tmp_path, [download.Pin("gone", f"{url}/gone", "0", 1)])


def test_present_needs_the_pinned_size(tmp_path):
    pin = download.Pin("m.bin", "http://127.0.0.1/m.bin", "0" * 64, 3)
    assert not download.present(tmp_path, pin)
    (tmp_path / "m.bin").write_bytes(b"ab")
    assert not download.present(tmp_path, pin)
    (tmp_path / "m.bin").write_bytes(b"abc")
    assert download.present(tmp_path, pin)
    assert download.sha256(tmp_path / "m.bin") == hashlib.sha256(b"abc").hexdigest()
