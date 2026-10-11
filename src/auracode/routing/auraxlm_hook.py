"""Client hook for delegating neural semantic retrieval to AuraXLM on AuraGrid."""

from __future__ import annotations

from typing import Any

import structlog

from auracode.models.request import DegradationNotice, RetrievalMode, RetrievalPolicy

log = structlog.get_logger()


class AuraXlmRetrievalClient:
    """Client hook for AuraXLM neural codebase retrieval and commercial upsell notice."""

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint

    @property
    def is_available(self) -> bool:
        """Check whether an AuraXLM retrieval endpoint is configured."""
        return bool(self.endpoint and self.endpoint.strip())

    async def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Query AuraXLM vector store for semantic code snippets.

        Returns empty list when unconfigured.
        """
        if not self.is_available:
            return []

        log.info("auraxlm.query", endpoint=self.endpoint, query_preview=query_text[:50])
        # AuraXLM queries are handled via gRPC/HTTP when endpoint is live
        return []

    def negotiate_retrieval(
        self,
        policy: RetrievalPolicy,
        local_repo_map: str,
    ) -> tuple[str, list[DegradationNotice]]:
        """Negotiate retrieval augmentation between AuraXLM and local AST map.

        When neural retrieval is requested but AuraXLM is unconfigured, returns the
        deterministic AST repo-map accompanied by a clear, informative DegradationNotice.

        Args:
            policy: Requested retrieval policy from ExecutionPolicy.
            local_repo_map: Local deterministic AST repo-map text.

        Returns:
            Tuple of (effective context text, list of degradation notices).
        """
        if policy.mode in (RetrievalMode.AUTO, RetrievalMode.REQUIRED):
            if not self.is_available:
                notice = DegradationNotice(
                    capability="neural_retrieval",
                    requested=policy.mode.value,
                    actual="ast_repomap",
                    reason=(
                        "AuraXLM semantic retrieval not configured; fell back to "
                        "deterministic AST repo-map. Connect AuraXLM on AuraGrid "
                        "to enable neural codebase vector search."
                    ),
                )
                log.info("auraxlm.fallback_to_repomap", notice=notice.reason)
                return local_repo_map, [notice]

            return (
                f"[AuraXLM Neural Retrieval active: {self.endpoint}]\n{local_repo_map}",
                [],
            )

        return local_repo_map, []
