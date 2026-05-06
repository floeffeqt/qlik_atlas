"""Abstract Git provider interface and data classes."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


@dataclass
class GitFileContent:
    """Result of reading a file from a Git repository."""
    content: str
    commit_sha: str
    file_path: str


@dataclass
class GitCommitInfo:
    """Metadata about a single Git commit."""
    sha: str
    message: str
    author_name: str
    author_email: str
    committed_at: str


class GitProvider(abc.ABC):
    """Abstract base class for Git hosting providers (GitHub, GitLab)."""

    @abc.abstractmethod
    async def read_file(
        self,
        repo: str,
        branch: str,
        file_path: str,
    ) -> GitFileContent:
        """Fetch a file's content and the latest commit SHA for that file."""

    @abc.abstractmethod
    async def get_commit(self, repo: str, sha: str) -> GitCommitInfo:
        """Return metadata for a specific commit."""

    @abc.abstractmethod
    async def write_file(
        self,
        repo: str,
        branch: str,
        file_path: str,
        content: str,
        commit_message: str,
        existing_sha: Optional[str] = None,
    ) -> GitCommitInfo:
        """Create or update a file in the repository and return the new commit."""

    @abc.abstractmethod
    async def verify_access(self, repo: str) -> bool:
        """Return True if the configured token can access the repository."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Clean up HTTP resources."""