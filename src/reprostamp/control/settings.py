import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path

from psycopg.conninfo import make_conninfo


@dataclass(frozen=True)
class Registration:
    id: str
    label: str
    path: Path


@dataclass(frozen=True)
class ProfileRegistration(Registration):
    repo_id: str
    base: str
    head: str


@dataclass(frozen=True)
class Settings:
    data: Path
    dsn: str
    origin: str
    repositories: dict[str, Registration]
    profiles: dict[str, ProfileRegistration]
    lease_seconds: int = 10

    @classmethod
    def local(cls, root: Path = Path.cwd()) -> "Settings":
        data = Path(os.environ.get("REPROSTAMP_DATA", root / ".reprostamp/prd03")).resolve()
        dsn = os.environ.get("REPROSTAMP_DATABASE_URL")
        if not dsn:
            password = (data / "postgres-password").read_text(encoding="ascii").strip()
            dsn = make_conninfo(host="127.0.0.1", port=os.environ.get("REPROSTAMP_PG_PORT", "55432"),
                                dbname="reprostamp", user="reprostamp", password=password)
        registry_file = os.environ.get("REPROSTAMP_REGISTRY")
        if registry_file:
            registry_path = Path(registry_file).resolve(strict=True)
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            root = registry_path.parent
        else:
            fixtures = {"checkout": "Discount checkout", "shipping": "Shipping threshold"}
            registry = {
                "repositories": {name: {"label": title, "path": f".reprostamp/{name}/repo"}
                                 for name, title in fixtures.items()},
                "profiles": {name: {"label": "Three-browser verification", "path": f"profiles/{name}.json",
                                    "repo_id": name, "base": f"{name}-base", "head": f"{name}-fixed"}
                             for name in fixtures},
            }
        repositories = {
            key: Registration(key, row["label"], (root / row["path"]).resolve())
            for key, row in registry["repositories"].items()
        }
        profiles = {
            key: ProfileRegistration(key, row["label"], (root / row["path"]).resolve(),
                                     row["repo_id"], row["base"], row["head"])
            for key, row in registry["profiles"].items()
        }
        if any(item.repo_id not in repositories for item in profiles.values()):
            raise ValueError("Every registered profile must refer to a registered repository.")
        origin = os.environ.get("REPROSTAMP_ORIGIN", "http://127.0.0.1:3000")
        return cls(data, dsn, origin, repositories, profiles)

    def owner_password(self) -> str:
        path = self.data / "owner-password"
        self.data.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.exists():
            with tempfile.NamedTemporaryFile(dir=self.data, mode="w", encoding="ascii") as pending:
                pending.write(secrets.token_urlsafe(32) + "\n")
                pending.flush()
                try:
                    os.link(pending.name, path)
                except FileExistsError:
                    pass
        return path.read_text(encoding="ascii").strip()
