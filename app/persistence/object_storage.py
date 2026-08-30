from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from app.config.settings import Settings
from app.persistence.errors import PersistenceConfigurationError

logger = logging.getLogger(__name__)


class ObjectStorageError(RuntimeError):
    """A private object could not be stored or retrieved safely."""


class ObjectNotFoundError(ObjectStorageError):
    """The requested private object does not exist."""


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    size_bytes: int
    checksum_sha256: str
    content_type: str
    provider_version: str | None = None


class ObjectStorage(Protocol):
    @property
    def provider(self) -> str: ...

    def ready(self) -> bool: ...

    def put_file(
        self,
        *,
        key: str,
        source: Path,
        content_type: str,
        checksum_sha256: str,
    ) -> ObjectMetadata: ...

    def download_file(self, *, key: str, destination: Path) -> ObjectMetadata: ...

    def stat(self, *, key: str) -> ObjectMetadata: ...

    def exists(self, *, key: str) -> bool: ...

    def delete(self, *, key: str) -> None: ...


def validate_object_key(value: str) -> str:
    cleaned = value.strip().replace("\\", "/")
    key = PurePosixPath(cleaned)
    if not cleaned or key.is_absolute() or ".." in key.parts or "." in key.parts:
        raise PersistenceConfigurationError("Object storage key is unsafe.")
    if any(not part or part in {".", ".."} for part in key.parts):
        raise PersistenceConfigurationError("Object storage key is unsafe.")
    return key.as_posix()


def source_object_key(owner_user_id: UUID, analysis_id: str, suffix: str) -> str:
    safe_analysis_id = _safe_identifier(analysis_id, "analysis")
    safe_suffix = suffix.lower()
    if not safe_suffix.startswith(".") or any(char in safe_suffix for char in "/\\"):
        raise PersistenceConfigurationError("Source video suffix is unsafe.")
    return validate_object_key(
        f"users/{owner_user_id}/analyses/{safe_analysis_id}/source/video{safe_suffix}"
    )


def artifact_object_key(
    owner_user_id: UUID,
    analysis_id: str,
    logical_key: str,
    checksum_sha256: str | None = None,
) -> str:
    safe_analysis_id = _safe_identifier(analysis_id, "analysis")
    safe_logical_key = validate_object_key(logical_key)
    logical = PurePosixPath(safe_logical_key)
    if checksum_sha256 is not None:
        if len(checksum_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in checksum_sha256
        ):
            raise PersistenceConfigurationError("Artifact checksum is unsafe.")
        logical = logical.parent / "versions" / checksum_sha256 / logical.name
    return validate_object_key(
        f"users/{owner_user_id}/analyses/{safe_analysis_id}/artifacts/{logical.as_posix()}"
    )


def build_object_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "local":
        return LocalObjectStorage(settings.local_storage_root)
    return S3ObjectStorage.from_settings(settings)


@dataclass(frozen=True)
class LocalObjectStorage:
    root: Path
    provider: str = "local"

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.expanduser().resolve())

    def ready(self) -> bool:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return self.root.is_dir()

    def put_file(
        self,
        *,
        key: str,
        source: Path,
        content_type: str,
        checksum_sha256: str,
    ) -> ObjectMetadata:
        destination = self._path(key)
        resolved_source = source.expanduser().resolve()
        if not resolved_source.is_file():
            raise ObjectStorageError("Source bytes are unavailable for local storage.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination != resolved_source:
            temporary = destination.with_name(f".{destination.name}.court4-upload")
            shutil.copyfile(resolved_source, temporary)
            temporary.replace(destination)
        metadata = ObjectMetadata(
            key=validate_object_key(key),
            size_bytes=destination.stat().st_size,
            checksum_sha256=_file_sha256(destination),
            content_type=content_type,
        )
        _verify_metadata(metadata, checksum_sha256, resolved_source.stat().st_size)
        return metadata

    def download_file(self, *, key: str, destination: Path) -> ObjectMetadata:
        source = self._path(key)
        if not source.is_file():
            raise ObjectNotFoundError("Private object was not found.")
        resolved_destination = destination.expanduser().resolve()
        resolved_destination.parent.mkdir(parents=True, exist_ok=True)
        if source != resolved_destination:
            temporary = resolved_destination.with_name(
                f".{resolved_destination.name}.court4-download"
            )
            shutil.copyfile(source, temporary)
            temporary.replace(resolved_destination)
        return ObjectMetadata(
            key=validate_object_key(key),
            size_bytes=source.stat().st_size,
            checksum_sha256=_file_sha256(source),
            content_type="application/octet-stream",
        )

    def stat(self, *, key: str) -> ObjectMetadata:
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFoundError("Private object was not found.")
        return ObjectMetadata(
            key=validate_object_key(key),
            size_bytes=path.stat().st_size,
            checksum_sha256=_file_sha256(path),
            content_type="application/octet-stream",
        )

    def exists(self, *, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, *, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        resolved = self.root.joinpath(*PurePosixPath(validate_object_key(key)).parts).resolve()
        if not resolved.is_relative_to(self.root):
            raise PersistenceConfigurationError("Local object path escaped its configured root.")
        return resolved


class S3ObjectStorage:
    provider = "s3"

    def __init__(self, *, client: object, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_settings(cls, settings: Settings) -> S3ObjectStorage:
        endpoint = settings.storage_s3_endpoint
        region = settings.storage_s3_region
        bucket = settings.storage_s3_bucket
        access_key = settings.storage_s3_access_key_id
        secret_key = settings.storage_s3_secret_access_key
        if not all(
            (
                endpoint,
                region,
                bucket,
                access_key,
                secret_key,
            )
        ):
            raise PersistenceConfigurationError(
                "S3 storage requires endpoint, region, bucket, access key ID, "
                "and secret access key."
            )
        assert endpoint is not None
        assert region is not None
        assert bucket is not None
        assert access_key is not None
        assert secret_key is not None
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - packaging failure
            raise PersistenceConfigurationError(
                "The S3 storage dependency is unavailable."
            ) from exc
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=access_key.get_secret_value(),
            aws_secret_access_key=secret_key.get_secret_value(),
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": settings.storage_s3_addressing_style},
            ),
        )
        return cls(client=client, bucket=bucket)

    def ready(self) -> bool:
        try:
            self._call("head_bucket", Bucket=self._bucket)
        except ObjectStorageError:
            return False
        return True

    def put_file(
        self,
        *,
        key: str,
        source: Path,
        content_type: str,
        checksum_sha256: str,
    ) -> ObjectMetadata:
        safe_key = validate_object_key(key)
        resolved = source.expanduser().resolve()
        if not resolved.is_file():
            raise ObjectStorageError("Source bytes are unavailable for object storage.")
        self._call(
            "upload_file",
            str(resolved),
            self._bucket,
            safe_key,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": {"court4-sha256": checksum_sha256},
            },
        )
        metadata = self.stat(key=safe_key)
        _verify_metadata(metadata, checksum_sha256, resolved.stat().st_size)
        return metadata

    def download_file(self, *, key: str, destination: Path) -> ObjectMetadata:
        safe_key = validate_object_key(key)
        metadata = self.stat(key=safe_key)
        resolved = destination.expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        temporary = resolved.with_name(f".{resolved.name}.court4-download")
        try:
            self._call("download_file", self._bucket, safe_key, str(temporary))
            checksum = _file_sha256(temporary)
            _verify_metadata(metadata, checksum, temporary.stat().st_size)
            temporary.replace(resolved)
        finally:
            temporary.unlink(missing_ok=True)
        return metadata

    def stat(self, *, key: str) -> ObjectMetadata:
        safe_key = validate_object_key(key)
        response = self._call("head_object", Bucket=self._bucket, Key=safe_key)
        if not isinstance(response, dict):
            raise ObjectStorageError("Object storage returned invalid metadata.")
        custom_metadata = response.get("Metadata") or {}
        checksum = (
            custom_metadata.get("court4-sha256") if isinstance(custom_metadata, dict) else None
        )
        if not isinstance(checksum, str) or len(checksum) != 64:
            raise ObjectStorageError("Object storage checksum metadata is missing.")
        return ObjectMetadata(
            key=safe_key,
            size_bytes=int(response["ContentLength"]),
            checksum_sha256=checksum,
            content_type=str(response.get("ContentType") or "application/octet-stream"),
            provider_version=(
                str(response["VersionId"]) if response.get("VersionId") is not None else None
            ),
        )

    def exists(self, *, key: str) -> bool:
        try:
            self.stat(key=key)
        except ObjectNotFoundError:
            return False
        return True

    def delete(self, *, key: str) -> None:
        self._call("delete_object", Bucket=self._bucket, Key=validate_object_key(key))

    def _call(self, method: str, *args: object, **kwargs: object) -> object:
        try:
            operation = getattr(self._client, method)
            return operation(*args, **kwargs)
        except Exception as exc:
            response = getattr(exc, "response", None)
            code = None
            if isinstance(response, dict):
                error = response.get("Error")
                if isinstance(error, dict):
                    code = error.get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise ObjectNotFoundError("Private object was not found.") from exc
            logger.warning("private_object_storage_operation_failed", extra={"operation": method})
            raise ObjectStorageError("Private object storage operation failed.") from exc


def _safe_identifier(value: str, label: str) -> str:
    if not value or len(value) > 64 or not all(char.isalnum() or char in "_-" for char in value):
        raise PersistenceConfigurationError(f"{label.capitalize()} identifier is unsafe.")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_metadata(metadata: ObjectMetadata, checksum_sha256: str, size_bytes: int) -> None:
    if metadata.size_bytes != size_bytes or metadata.checksum_sha256 != checksum_sha256:
        raise ObjectStorageError("Private object failed size or checksum verification.")
