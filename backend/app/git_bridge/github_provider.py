"""GitHub REST API v3 implementation of GitProvider."""
from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

from .provider import GitCommitInfo, GitFileContent, GitProvider

logger = logging.getLogger("atlas.git.github")

_DEFAULT_BASE = "https://api.github.com"


class GitHubProvider(GitProvider):
    def __init__(self, token: str, base_url: str | None = None) -> None:
        self._base = (base_url or _DEFAULT_BASE).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=httpx.Timeout(30.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def read_file(self, repo: str, branch: str, file_path: str) -> GitFileContent:
        path = file_path.lstrip("/")
        url = f"/repos/{repo}/contents/{path}"
        resp = await self._client.get(url, params={"ref": branch})
        resp.raise_for_status()
        data = resp.json()

        if data.get("encoding") == "base64":
            content = base64.b64decode(data["content"]).decode("utf-8")
        else:
            content = data.get("content", "")

        # Get latest commit SHA for this file on this branch
        commits_url = f"/repos/{repo}/commits"
        commits_resp = await self._client.get(
            commits_url, params={"sha": branch, "path": path, "per_page": 1}
        )
        commits_resp.raise_for_status()
        commits = commits_resp.json()
        commit_sha = commits[0]["sha"] if commits else data.get("sha", "")

        return GitFileContent(content=content, commit_sha=commit_sha, file_path=path)

    async def get_commit(self, repo: str, sha: str) -> GitCommitInfo:
        url = f"/repos/{repo}/commits/{sha}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        data = resp.json()
        commit = data["commit"]
        return GitCommitInfo(
            sha=data["sha"],
            message=commit["message"],
            author_name=commit["author"]["name"],
            author_email=commit["author"]["email"],
            committed_at=commit["committer"]["date"],
        )

    async def write_file(
        self,
        repo: str,
        branch: str,
        file_path: str,
        content: str,
        commit_message: str,
        existing_sha: Optional[str] = None,
    ) -> GitCommitInfo:
        path = file_path.lstrip("/")
        url = f"/repos/{repo}/contents/{path}"

        # If no existing_sha provided, try to get it (file may already exist)
        if existing_sha is None:
            try:
                check = await self._client.get(url, params={"ref": branch})
                if check.status_code == 200:
                    existing_sha = check.json().get("sha")
            except httpx.HTTPError:
                pass

        body: dict = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if existing_sha:
            body["sha"] = existing_sha

        resp = await self._client.put(url, json=body)
        resp.raise_for_status()
        data = resp.json()
        c = data["commit"]
        return GitCommitInfo(
            sha=c["sha"],
            message=c["message"],
            author_name=c["author"]["name"],
            author_email=c["author"]["email"],
            committed_at=c["committer"]["date"],
        )

    async def verify_access(self, repo: str) -> bool:
        try:
            resp = await self._client.get(f"/repos/{repo}")
            return resp.status_code == 200
        except httpx.HTTPError:
            logger.warning("GitHub access check failed for %s", repo)
            return False