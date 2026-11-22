import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .profile import PolicyError, Profile


OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
REGULAR_MODES = {"100644", "100755"}
UNSAFE_PATH = re.compile(r"[\\\x00-\x1f\x7f]")


class RepositoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class Entry:
    mode: str
    blob: str


class Repository:
    def __init__(self, path: Path):
        self.path = path
        self.env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
        self.env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
        root = self.git("rev-parse", "--show-toplevel").decode().rstrip("\n")
        if Path(root).resolve() != path:
            raise RepositoryError("--repo must point to the root of a local Git checkout.")

    def git(self, *arguments: str, stdout=subprocess.PIPE) -> bytes:
        try:
            completed = subprocess.run(
                ["git", "--no-replace-objects", "-C", str(self.path), *arguments],
                env=self.env, stdout=stdout, stderr=subprocess.PIPE, check=True, timeout=30,
            )
            return completed.stdout or b""
        except subprocess.CalledProcessError as error:
            raise RepositoryError(error.stderr.decode(errors="replace").strip()) from error
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RepositoryError(str(error)) from error

    def resolve(self, ref: str) -> str:
        commit = self.git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()
        if not OBJECT_ID.fullmatch(commit):
            raise RepositoryError(f"Git did not resolve {ref!r} to a commit SHA.")
        return commit

    def tree(self, commit: str) -> dict[str, Entry]:
        entries = {}
        canonical_paths = {}
        listing = self.git("ls-tree", "-rz", "--full-tree", commit)
        for record in listing.split(b"\0")[:-1]:
            metadata, _, raw_path = record.partition(b"\t")
            mode, kind, blob = metadata.decode().split()
            try:
                path = raw_path.decode("utf-8")
            except UnicodeDecodeError as error:
                raise PolicyError("unsupported_repository_entry", "Tracked paths must be UTF-8.") from error

            if kind != "blob" or mode not in REGULAR_MODES:
                raise PolicyError("unsupported_repository_entry", f"Unsupported Git entry {path!r} ({mode} {kind}).")
            parts = path.split("/")
            if UNSAFE_PATH.search(path) or any(part.lower() in {"", ".", "..", ".git"} for part in parts):
                raise PolicyError("unsupported_repository_entry", f"Unsupported Git path {path!r}.")
            for index in range(1, len(parts) + 1):
                prefix = "/".join(parts[:index])
                folded = unicodedata.normalize("NFC", prefix).casefold()
                if canonical_paths.setdefault(folded, prefix) != prefix:
                    raise PolicyError("unsupported_repository_entry", f"Case or Unicode collision at {path!r}.")
            entries[path] = Entry(mode, blob)
        return entries

    def export(self, entries: dict[str, Entry], target: Path) -> None:
        target.mkdir()
        for path, entry in entries.items():
            file = target / path
            file.parent.mkdir(parents=True, exist_ok=True)
            with file.open("xb") as sink:
                self.git("cat-file", "blob", entry.blob, stdout=sink)
            file.chmod(0o755 if entry.mode == "100755" else 0o644)
        for directory, _, _ in os.walk(target):
            Path(directory).chmod(0o755)


def changed_paths(base: dict[str, Entry], head: dict[str, Entry], profile: Profile) -> list[str]:
    changes = sorted(path for path in base.keys() | head.keys() if base.get(path) != head.get(path))
    rejected = [path for path in changes if not profile.allows(path)]
    if rejected:
        raise PolicyError("disallowed_change", "Changes outside the editable surface: " + ", ".join(repr(p) for p in rejected))
    if not {"package.json", "package-lock.json"} <= base.keys() & head.keys():
        raise PolicyError("missing_dependency_lock", "Both commits must track package.json and package-lock.json at the root.")
    return changes
