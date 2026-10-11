import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GitMirrorService:
    """
    Manages bare/mirror Git repositories for collaborative offline coding.
    When running on AuraGrid, the mirror path typically points to a shared volume
    (e.g., GridRoot/app_data/auracode/repos) to allow multiple nodes to synchronize.
    """

    def __init__(self, storage_path: str | None = None):
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            env_path = os.environ.get("AURACODE_GIT_MIRROR_PATH")
            if env_path:
                self.storage_path = Path(env_path)
            else:
                self.storage_path = Path.home() / ".auracode" / "repos"

        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized GitMirrorService with storage path: {self.storage_path}")

    def _get_repo_path(self, repo_name: str) -> Path:
        if not repo_name.endswith(".git"):
            repo_name = f"{repo_name}.git"
        return self.storage_path / repo_name

    def init_bare(self, repo_name: str) -> Path:
        """Initializes a new bare repository."""
        repo_path = self._get_repo_path(repo_name)
        if repo_path.exists():
            logger.info(f"Bare repo {repo_name} already exists at {repo_path}")
            return repo_path

        logger.info(f"Initializing bare repo {repo_name} at {repo_path}")
        repo_path.mkdir(parents=True, exist_ok=True)
        self._run_git(["init", "--bare"], cwd=repo_path)
        return repo_path

    def clone_mirror(self, source_url: str, repo_name: str) -> Path:
        """Clones a remote repository as a local mirror."""
        repo_path = self._get_repo_path(repo_name)
        if repo_path.exists():
            logger.info(f"Mirror repo {repo_name} already exists at {repo_path}. Fetching instead.")
            self.fetch(repo_name)
            return repo_path

        logger.info(f"Cloning mirror from {source_url} to {repo_path}")
        self._run_git(["clone", "--mirror", source_url, str(repo_path)])
        return repo_path

    def fetch(self, repo_name: str):
        """Fetches updates for an existing mirror."""
        repo_path = self._get_repo_path(repo_name)
        if not repo_path.exists():
            raise FileNotFoundError(f"Repo {repo_name} does not exist at {repo_path}")

        logger.info(f"Fetching updates for {repo_name}")
        self._run_git(["fetch", "--all"], cwd=repo_path)

    def _run_git(self, args: list[str], cwd: Path | None = None):
        """Helper to run git commands."""
        cmd = ["git"] + args
        try:
            result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Git command failed: {' '.join(cmd)}\nStdout: {e.stdout}\nStderr: {e.stderr}"
            )
            raise RuntimeError(f"Git operation failed: {e.stderr}") from e
