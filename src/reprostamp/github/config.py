import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, PositiveInt, field_validator

from ..control.settings import Settings, Registration


REPO_PATH = re.compile(r"[a-zA-Z0-9-]+/[a-zA-Z0-9_.-]+")
SHA = re.compile(r"[0-9a-f]{40}")


class Pilot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    app_id: PositiveInt
    installation_id: PositiveInt
    repository_id: PositiveInt
    repository: str
    profile_id: str
    dashboard_url: str
    webhook_secret_file: str
    private_key_file: str

    @field_validator("repository")
    @classmethod
    def repository_name(cls, value: str) -> str:
        if not REPO_PATH.fullmatch(value) or value.split("/")[1] in {".", ".."} or value.endswith(".git"):
            raise ValueError("Use the approved GitHub owner/repository name without the .git suffix.")
        return value

    @field_validator("dashboard_url")
    @classmethod
    def evidence_url(cls, value: str) -> str:
        url = urlsplit(value)
        if (url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1"))) or (
            not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/")
        ):
            raise ValueError("Use an HTTPS dashboard origin or an HTTP loopback origin for same-machine review.")
        return value.rstrip("/")

    @property
    def scope(self) -> tuple[int, int, str]:
        return self.installation_id, self.repository_id, self.profile_id

    def registered_repository(self, settings: Settings) -> Registration:
        profile = settings.profiles.get(self.profile_id)
        if profile is None:
            raise ValueError("Register the pilot profile and its local checkout before starting the integration.")
        return settings.repositories[profile.repo_id]

    @classmethod
    def from_file(cls, path: Path) -> "Pilot":
        pilot = cls.model_validate_json(path.read_bytes())
        for field in ("webhook_secret_file", "private_key_file"):
            setattr(pilot, field, str((path.parent / getattr(pilot, field)).resolve(strict=True)))
        return pilot
