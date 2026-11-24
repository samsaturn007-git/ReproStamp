import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.client import HTTPException

from ..repository import Repository, RepositoryError
from .config import Pilot, SHA


CHECK_NAME = "ReproStamp"
API_VERSION = "2026-03-10"


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def pr_refs(pr: dict, repository_id: int) -> tuple[str, str] | None:
    try:
        if any(type(pr[side]["repo"]["id"]) is not int or pr[side]["repo"]["id"] != repository_id
               for side in ("base", "head")):
            return None
        base, head = (pr[side]["sha"] for side in ("base", "head"))
    except (KeyError, TypeError):
        return None
    if all(isinstance(sha, str) and SHA.fullmatch(sha) for sha in (base, head)):
        return base, head
    return None


class GitHub:
    def __init__(self, pilot: Pilot, *, origin: str = "https://api.github.com"):
        self.pilot = pilot
        self.origin = origin
        self.repo_path = f"/repos/{pilot.repository}"
        self.opener = urllib.request.build_opener(NoRedirect())
        self.access_token = None
        self.expires_at = 0.0

    def call(self, method: str, path: str, token: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.origin + path, None if body is None else json.dumps(body).encode(),
            method=method, headers={"Accept": "application/vnd.github+json", "Content-Type": "application/json",
                                    "User-Agent": "ReproStamp", "X-GitHub-Api-Version": API_VERSION,
                                    "Authorization": f"Bearer {token}"},
        )
        try:
            with self.opener.open(request, timeout=8) as response:
                data = json.load(response)
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object.")
                return data
        except urllib.error.HTTPError as error:
            error.close()
            raise GitHubError(f"GitHub returned HTTP {error.code} for {method}.", error.code) from None
        except (OSError, ValueError, HTTPException):
            raise GitHubError(f"GitHub response unavailable for {method}.") from None

    def app_jwt(self) -> str:
        now = int(time.time())
        claims = {"iat": now - 60, "exp": now + 540, "iss": str(self.pilot.app_id)}
        payload = b64url(b'{"alg":"RS256","typ":"JWT"}') + b"." + b64url(json.dumps(claims).encode())
        try:
            signature = subprocess.run(
                ["openssl", "dgst", "-sha256", "-sign", self.pilot.private_key_file],
                input=payload, capture_output=True, check=True, timeout=5,
            ).stdout
        except (OSError, subprocess.SubprocessError) as error:
            raise GitHubError("Could not sign with the GitHub App private key.") from error
        return (payload + b"." + b64url(signature)).decode("ascii")

    def token(self) -> str:
        if self.access_token and time.time() < self.expires_at - 60:
            return self.access_token
        path = f"/app/installations/{self.pilot.installation_id}/access_tokens"
        result = self.call("POST", path, self.app_jwt(), {
            "repository_ids": [self.pilot.repository_id],
            "permissions": {"contents": "read", "pull_requests": "read", "checks": "write"},
        })
        self.access_token = result["token"]
        self.expires_at = datetime.fromisoformat(result["expires_at"]).timestamp()
        return self.access_token

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        try:
            return self.call(method, self.repo_path + path, self.token(), body)
        except GitHubError as error:
            if error.status == 401:
                self.access_token = None
            raise

    def pull_refs(self, number: int) -> tuple[str, str] | None:
        pr = self.request("GET", f"/pulls/{number}")
        if pr.get("state") != "open" or pr.get("number") != number:
            return None
        return pr_refs(pr, self.pilot.repository_id)

    def find_check(self, head: str, external_id: str) -> int | None:
        matches = []
        page = 1
        while True:
            params = urllib.parse.urlencode({
                "check_name": CHECK_NAME, "app_id": self.pilot.app_id, "filter": "all", "per_page": 100, "page": page,
            })
            result = self.request("GET", f"/commits/{head}/check-runs?{params}")
            rows = result["check_runs"]
            matches.extend(row["id"] for row in rows if row.get("external_id") == external_id
                           and row.get("head_sha") == head and row.get("name") == CHECK_NAME
                           and (row.get("app") or {}).get("id") == self.pilot.app_id)
            if len(rows) < 100:
                break
            page += 1
        if len(matches) > 1:
            raise GitHubError("Multiple GitHub checks match the same local check identity.")
        return matches[0] if matches else None

    def publish(self, head: str, external_id: str, remote_id: int | None, body: dict) -> int:
        data = {"name": CHECK_NAME, "external_id": external_id, **body}
        if remote_id is None:
            return self.request("POST", "/check-runs", {**data, "head_sha": head})["id"]
        return self.request("PATCH", f"/check-runs/{remote_id}", data)["id"]

    def fetch_commits(self, repo: Repository, base: str, head: str) -> None:
        missing = []
        for sha in dict.fromkeys((base, head)):
            if not SHA.fullmatch(sha):
                raise ValueError("Expected an immutable GitHub commit SHA.")
            try:
                repo.resolve(sha)
            except RepositoryError:
                missing.append(sha)
        if missing:
            url = f"https://github.com/{self.pilot.repository}.git"
            basic = base64.b64encode(f"x-access-token:{self.token()}".encode()).decode()
            env = {k: v for k, v in repo.env.items() if not k.startswith("REPROSTAMP_GITHUB_")}
            env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0=f"http.{url}.extraHeader",
                       GIT_CONFIG_VALUE_0=f"Authorization: Basic {basic}", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_CONFIG_NOSYSTEM="1")
            try:
                subprocess.run(
                    ["git", "-C", str(repo.path), "-c", "credential.helper=", "-c", "http.followRedirects=false",
                     "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
                     "fetch", "--no-tags", "--no-recurse-submodules", "--no-auto-maintenance",
                     "--no-write-fetch-head", "--", url, *missing],
                    env=env, capture_output=True, timeout=40, check=True,
                )
            except (OSError, subprocess.SubprocessError):
                raise GitHubError("Could not fetch the approved commit objects from GitHub.") from None
        if any(repo.resolve(sha) != sha for sha in (base, head)):
            raise GitHubError("The approved commits did not resolve to the requested object IDs.")
