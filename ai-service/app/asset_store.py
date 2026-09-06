import os
import tempfile
from pathlib import Path


class LocalAssetStore:
    """Filesystem implementation of the replaceable binary-object boundary."""

    backend = "local"

    def __init__(self, root: Path):
        self.root = root

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes) -> str:
        target = self.root / key
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        return str(target.resolve())

    def resolve(self, location: str) -> Path:
        return Path(location)

    def check(self) -> None:
        if not self.root.is_dir():
            raise RuntimeError("asset store directory is unavailable")


class S3AssetStore:
    """Private S3-compatible storage with a bounded local read-through cache."""

    backend = "s3"

    def __init__(self, root: Path, bucket: str, prefix: str = "ai-assets",
                 endpoint_url: str | None = None, region: str | None = None, client=None):
        if not bucket:
            raise RuntimeError("S3 bucket is required")
        self.root, self.bucket, self.prefix = root, bucket, prefix.strip("/")
        if client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError("Install boto3 to use the S3 asset backend") from exc
            client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
        self.client = client

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.check()

    def _object_key(self, key: str) -> str:
        safe = Path(key).name
        return f"{self.prefix}/{safe}" if self.prefix else safe

    def put(self, key: str, data: bytes) -> str:
        object_key = self._object_key(key)
        self.client.put_object(Bucket=self.bucket, Key=object_key, Body=data)
        return f"s3://{self.bucket}/{object_key}"

    def resolve(self, location: str) -> Path:
        expected = f"s3://{self.bucket}/"
        if not location.startswith(expected):
            raise ValueError("asset location is outside the configured S3 bucket")
        object_key = location[len(expected):]
        target = self.root / Path(object_key).name
        if not target.exists():
            fd, temporary_name = tempfile.mkstemp(dir=self.root, suffix=".tmp")
            os.close(fd)
            temporary = Path(temporary_name)
            try:
                self.client.download_file(self.bucket, object_key, str(temporary))
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return target

    def check(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)


def create_asset_store(backend: str, root: Path, **options):
    if backend == "local":
        return LocalAssetStore(root)
    if backend == "s3":
        return S3AssetStore(root, bucket=options.get("bucket"), prefix=options.get("prefix", "ai-assets"),
                            endpoint_url=options.get("endpoint_url"), region=options.get("region"),
                            client=options.get("client"))
    raise RuntimeError(f"Unsupported asset backend: {backend}")
