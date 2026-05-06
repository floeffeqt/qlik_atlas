"""GitLab REST API v4 implementation of GitProvider."""
from __future__ import annotations

import base64
import logging
from typing import Optional
from urllib.parse import quote as urlquote

import httpx

from .provider import GitCommitInfo, GitFileContent, GitProvider

logger = logging.getLogger("atlas.git.gitlab")

_DEFAULT_BASE = "https://gitlab.com"


def _encode_path(path: str) -> str:
    """URL-encode a file path for GitLab API (slashes must be encoded)."""
    return urlquote(path.lstrip("/"), safe="")


class GitLabProvider(GitProvider):
    def __init__(self, token: str, base_url: str | None = None) -> None:
        base = (base_url or _DEFAULT_BASE).rstrip("/")
        self._api = f"{base}/api/v4"
        self._client = httpx.AsyncClient(
            base_url=self._api,
            headers={"PRIVATE-TOKEN": token},
            timeout=httpx.Timeout(30.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _project_path(self, repo: str) -> str:
        """repo can be numeric project ID or 'namespace/project' URL-encoded."""
        return urlquote(repo, safe="")

    async def read_file(self, repo: str, branch: str, file_path: str) -> GitFileContent:
        proj = self._project_path(repo)
        encoded_path = _encode_path(file_path)
        url = f"/projects/{proj}/repository/files/{encoded_path}"
        resp = await self._client.get(url, params={"ref": branch})
        resp.raise_for_status()
        data = resp.json()

        content_raw = data.get("content", "")
        encoding = data.get("encoding", "base64")
        if encoding == "base64":
            content = base64.b64decode(content_raw).decode("utf-8")
        else:
            content = content_raw

        commit_sha = data.get("last_commit_id", data.get("commit_id", ""))

        return GitFileContent(
            content=content, commit_sha=commit_sha, file_path=file_path.lstrip("/")
        )

    async def get_commit(self, repo: str, sha: str) -> GitCommitInfo:
        proj = self._project_path(repo)
        url = f"/projects/{proj}/repository/commits/{sha}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return GitCommitInfo(
            sha=data["id"],
            message=data["message"],
            author_name=data["author_name"],
            author_email=data["author_email"],
            committed_at=data["committed_date"],
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
        proj = self._project_path(repo)
        encoded_path = _encode_path(file_path)
        url = f"/projects/{proj}/repository/files/{encoded_path}"

        body = {
            "branch": branch,
            "content": content,
            "commit_message": commit_message,
        }

        # Check if file exists to decide create vs. update
        check = await self._client.head(url, params={"ref": branch})
        if check.status_code == 200:
            resp = await self._client.put(url, json=body)
        else:
            resp = await self._client.post(url, json=body)

        resp.raise_for_status()
        data = resp.json()
        branch_ref = data.get("branch", branch)

        # Fetch the new commit info
        commits_url = f"/projects/{proj}/repository/commits"
        commits_resp = await self._client.get(
            commits_url, params={"ref_name": branch_ref, "per_page": 1}
        )
        commits_resp.raise_for_status()
        commits = commits_resp.json()
        if commits:
            return GitCommitInfo(
                sha=commits[0]["id"],
                message=commits[0]["message"],
                author_name=commits[0]["author_name"],
                author_email=commits[0]["author_email"],
                committed_at=commits[0]["committed_date"],
            )
        return GitCommitInfo(
            sha="", message=commit_message, author_name="", author_email="", committed_at=""
        )

    async def verify_access(self, repo: str) -> bool:
        try:
            proj = self._project_path(repo)
            resp = await self._client.get(f"/projects/{proj}")
            return resp.status_code == 200
        except httpx.HTTPError:
            logger.warning("GitLab access check failed for %s", repo)
            return False