from pathlib import Path

import pytest

from app.asset_store import LocalAssetStore, S3AssetStore, create_asset_store


def test_local_asset_store_round_trip(tmp_path):
    store = LocalAssetStore(tmp_path / "uploads")
    store.initialize()
    location = store.put("image.webp", b"real-image-bytes")
    assert Path(location).read_bytes() == b"real-image-bytes"
    assert not (tmp_path / "uploads" / "image.webp.tmp").exists()
    store.check()


def test_unsupported_asset_backend_fails_explicitly(tmp_path):
    with pytest.raises(RuntimeError, match="Unsupported"):
        create_asset_store("ftp", tmp_path)


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.checked = False

    def head_bucket(self, Bucket):
        self.checked = Bucket == "private-assets"

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.objects[(bucket, key)])


def test_s3_asset_store_round_trip_and_cache(tmp_path):
    client = FakeS3()
    store = S3AssetStore(tmp_path / "cache", "private-assets", "tenant/a", client=client)
    store.initialize()
    location = store.put("../image.webp", b"remote-image")
    assert location == "s3://private-assets/tenant/a/image.webp"
    assert store.resolve(location).read_bytes() == b"remote-image"
    assert client.checked


def test_s3_rejects_foreign_bucket_location(tmp_path):
    store = S3AssetStore(tmp_path, "ours", client=FakeS3())
    with pytest.raises(ValueError, match="outside"):
        store.resolve("s3://theirs/asset.png")
