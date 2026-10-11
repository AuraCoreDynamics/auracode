import logging
from pathlib import Path

from .mirror_service import GitMirrorService

logger = logging.getLogger(__name__)


class WorkspaceProvider:
    """
    Manages local workspace clones from bare/mirror repositories.
    """

    def __init__(self, mirror_service: GitMirrorService):
        self.mirror_service = mirror_service

    def clone_workspace(self, repo_name: str, target_dir: str | Path) -> Path:
        """
        Clones a workspace from the local bare mirror.
        """
        target_path = Path(target_dir)
        repo_path = self.mirror_service._get_repo_path(repo_name)

        if not repo_path.exists():
            raise FileNotFoundError(
                f"Bare repo {repo_name} does not exist. Cannot clone workspace."
            )

        if target_path.exists() and any(target_path.iterdir()):
            logger.info(
                f"Target directory {target_path} is not empty. Assuming workspace already exists."
            )
            return target_path

        logger.info(f"Cloning workspace for {repo_name} from {repo_path} to {target_path}")
        target_path.mkdir(parents=True, exist_ok=True)
        self.mirror_service._run_git(["clone", str(repo_path), str(target_path)])
        return target_path

    def push_workspace(self, workspace_dir: str | Path, branch: str = "main"):
        """
        Pushes changes from the workspace back to the local bare mirror.
        """
        workspace_path = Path(workspace_dir)
        logger.info(f"Pushing workspace {workspace_path} to mirror")
        self.mirror_service._run_git(["push", "origin", branch], cwd=workspace_path)

    def pull_workspace(self, workspace_dir: str | Path, branch: str = "main"):
        """
        Pulls changes from the local bare mirror to the workspace.
        """
        workspace_path = Path(workspace_dir)
        logger.info(f"Pulling workspace {workspace_path} from mirror")
        self.mirror_service._run_git(["pull", "origin", branch], cwd=workspace_path)
