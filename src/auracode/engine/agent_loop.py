"""Autonomous self-healing agent execution loop with verification gates."""

from __future__ import annotations

import asyncio
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from auracode.models.request import (
    EngineRequest,
    EngineResponse,
    ExecutionMetadata,
    RequestIntent,
)
from auracode.models.verification import (
    AgentLoopResult,
    RemediationBudget,
    RemediationStep,
    VerificationCommand,
    VerificationResult,
)
from auracode.routing.artifacts import execute_modifications, parse_artifact_payload
from auracode.utils.journal import FileJournal

if TYPE_CHECKING:
    from auracode.engine.core import AuraCodeEngine

log = structlog.get_logger()


class AgenticExecutionLoop:
    """Coordinates autonomous code generation, verification, and self-healing retries."""

    def __init__(
        self,
        engine: AuraCodeEngine,
        journal: FileJournal | None = None,
        event_bus: Any | None = None,
    ) -> None:
        self.engine = engine
        self.journal = journal or getattr(engine, "_journal", None) or FileJournal()
        self.engine._journal = self.journal
        self.event_bus = event_bus or getattr(engine, "event_bus", None)

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_bus:
            try:
                self.event_bus.broadcast(event_type, payload)
            except Exception as exc:
                log.debug("agent_loop.event_broadcast_failed", error=str(exc))

    async def run(
        self,
        request: EngineRequest,
        verification: VerificationCommand | None = None,
        budget: RemediationBudget | None = None,
    ) -> AgentLoopResult:
        """Run the autonomous agent loop with verification and bounded self-healing.

        Args:
            request: Initial engine request to execute.
            verification: Optional verification command to test code outcomes.
            budget: Remediation budget limiting retry turns.

        Returns:
            An AgentLoopResult describing outcome, verifications, and rollback token.
        """
        budget_state = RemediationBudget(
            max_attempts=(budget.max_attempts if budget else 3),
            current_attempt=0,
        )
        snapshot_id = self.journal.create_snapshot(tag=f"req_{request.request_id}")
        self._emit(
            "journal.snapshot_created",
            {"snapshot_id": snapshot_id, "request_id": request.request_id},
        )
        remediations: list[RemediationStep] = []

        if verification is not None and not self.engine.config.permissions.allow_shell_commands:
            log.warn("agent_loop.permission_denied", reason="allow_shell_commands=False")
            self._emit(
                "agent.step_completed",
                {"request_id": request.request_id, "status": "permission_denied", "attempt": 0},
            )
            return AgentLoopResult(
                status="permission_denied",
                snapshot_id=snapshot_id,
                rollback_available=True,
            )

        initial_options = dict(request.options or {})
        initial_options["_preserve_journal"] = True
        current_req = EngineRequest(
            request_id=request.request_id,
            intent=request.intent,
            prompt=request.prompt,
            context=request.context,
            adapter_name=request.adapter_name,
            options=initial_options,
            execution_policy=request.execution_policy,
        )
        work_dir = (
            request.context.working_directory
            if (request.context and request.context.working_directory)
            else "."
        )
        last_response: EngineResponse | None = None

        while budget_state.current_attempt <= budget_state.max_attempts:
            self._emit(
                "agent.step_started",
                {
                    "request_id": request.request_id,
                    "attempt": budget_state.current_attempt + 1,
                    "intent": request.intent.value,
                },
            )
            last_response = await self.engine.execute(current_req)
            if last_response.error:
                self._emit(
                    "agent.step_completed",
                    {
                        "request_id": request.request_id,
                        "status": "error",
                        "attempt": budget_state.current_attempt + 1,
                    },
                )
                return AgentLoopResult(
                    status="error",
                    final_response=last_response,
                    remediations=remediations,
                    snapshot_id=snapshot_id,
                    rollback_available=True,
                )

            # Parse and apply structured modifications
            payload = parse_artifact_payload(last_response.content)
            if payload is not None:
                if not self.engine.config.permissions.allow_file_write:
                    log.warn("agent_loop.permission_denied", reason="allow_file_write=False")
                    return AgentLoopResult(
                        status="permission_denied",
                        final_response=last_response,
                        remediations=remediations,
                        snapshot_id=snapshot_id,
                        rollback_available=True,
                    )

                # Pre-capture original contents for journal recording
                work_path = Path(work_dir).resolve()
                before_map: dict[str, str | None] = {}
                for mod in payload.modifications:
                    target_p = (work_path / mod.file_path).resolve()
                    if target_p.is_file():
                        before_map[mod.file_path] = target_p.read_text(
                            encoding="utf-8", errors="replace"
                        )
                    else:
                        before_map[mod.file_path] = None

                results = execute_modifications(payload, work_dir)
                if any(not r.success for r in results):
                    log.error("agent_loop.artifact_failed", results=[r.__dict__ for r in results])
                else:
                    for mod in payload.modifications:
                        target_p = (work_path / mod.file_path).resolve()
                        after_content = (
                            target_p.read_text(encoding="utf-8", errors="replace")
                            if target_p.is_file()
                            else None
                        )
                        self.journal.record(
                            path=str(target_p),
                            action=mod.modification_type,
                            before_content=before_map.get(mod.file_path),
                            after_content=after_content,
                        )

            if verification is None:
                self._emit(
                    "agent.step_completed",
                    {
                        "request_id": request.request_id,
                        "status": "success",
                        "attempt": budget_state.current_attempt + 1,
                    },
                )
                return AgentLoopResult(
                    status="success",
                    final_response=last_response,
                    remediations=remediations,
                    snapshot_id=snapshot_id,
                    rollback_available=True,
                )

            self._emit(
                "verification.executed",
                {
                    "command": verification.command,
                    "attempt": budget_state.current_attempt + 1,
                },
            )
            verif_result = await self._run_verification(verification)
            self._emit(
                "verification.result",
                {
                    "command": verification.command,
                    "passed": verif_result.passed,
                    "returncode": verif_result.exit_code,
                    "attempt": budget_state.current_attempt + 1,
                },
            )
            step = RemediationStep(
                attempt=budget_state.current_attempt + 1,
                verification=verif_result,
                diagnosis="Passed" if verif_result.passed else "Verification failed",
            )
            remediations.append(step)

            if verif_result.passed:
                enriched_response = self._attach_verification_metadata(
                    last_response, outcome="passed"
                )
                self._emit(
                    "agent.step_completed",
                    {
                        "request_id": request.request_id,
                        "status": "success",
                        "attempt": budget_state.current_attempt + 1,
                    },
                )
                return AgentLoopResult(
                    status="success",
                    final_response=enriched_response,
                    remediations=remediations,
                    snapshot_id=snapshot_id,
                    rollback_available=True,
                )

            budget_state = RemediationBudget(
                max_attempts=budget_state.max_attempts,
                current_attempt=budget_state.current_attempt + 1,
            )

            if budget_state.current_attempt >= budget_state.max_attempts:
                enriched_response = self._attach_verification_metadata(
                    last_response, outcome="remediation_exhausted"
                )
                self._emit(
                    "agent.step_completed",
                    {
                        "request_id": request.request_id,
                        "status": "remediation_exhausted",
                        "attempt": budget_state.current_attempt,
                    },
                )
                return AgentLoopResult(
                    status="remediation_exhausted",
                    final_response=enriched_response,
                    remediations=remediations,
                    snapshot_id=snapshot_id,
                    rollback_available=True,
                )

            current_req = self._build_remediation_request(
                original_request=request,
                attempt=budget_state.current_attempt,
                verification=verification,
                result=verif_result,
            )

        self._emit(
            "agent.step_completed",
            {
                "request_id": request.request_id,
                "status": "remediation_exhausted",
                "attempt": budget_state.current_attempt,
            },
        )
        return AgentLoopResult(
            status="remediation_exhausted",
            final_response=last_response,
            remediations=remediations,
            snapshot_id=snapshot_id,
            rollback_available=True,
        )

    async def rollback(self, snapshot_id: str) -> list[str]:
        """Roll back filesystem modifications to the specified snapshot checkpoint."""
        restored = self.journal.rollback_snapshot(snapshot_id)
        self._emit(
            "journal.rollback_executed",
            {"snapshot_id": snapshot_id, "restored_count": len(restored)},
        )
        return restored

    async def _run_verification(self, verif: VerificationCommand) -> VerificationResult:
        """Run verification command in a worker thread."""
        return await asyncio.to_thread(self._execute_command_sync, verif)

    def _execute_command_sync(self, verif: VerificationCommand) -> VerificationResult:
        t0 = time.perf_counter()
        use_shell = sys.platform == "win32"
        cmd_args = verif.command if use_shell else shlex.split(verif.command)

        try:
            proc = subprocess.run(
                cmd_args,
                shell=use_shell,
                stdin=subprocess.DEVNULL,
                cwd=verif.working_directory,
                capture_output=True,
                text=True,
                timeout=verif.timeout_seconds,
            )
            dur_ms = int((time.perf_counter() - t0) * 1000)
            return VerificationResult(
                command=verif.command,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                passed=(proc.returncode == 0),
                duration_ms=dur_ms,
            )
        except subprocess.TimeoutExpired:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            return VerificationResult(
                command=verif.command,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {verif.timeout_seconds}s",
                passed=False,
                duration_ms=dur_ms,
            )
        except Exception as exc:
            dur_ms = int((time.perf_counter() - t0) * 1000)
            return VerificationResult(
                command=verif.command,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                passed=False,
                duration_ms=dur_ms,
            )

    def _build_remediation_request(
        self,
        original_request: EngineRequest,
        attempt: int,
        verification: VerificationCommand,
        result: VerificationResult,
    ) -> EngineRequest:
        tail_out = result.stdout[-1500:] if result.stdout else ""
        tail_err = result.stderr[-1500:] if result.stderr else ""
        prompt = (
            f"The previous implementation failed verification command `{verification.command}` "
            f"(exit code: {result.exit_code}).\n"
            f"STDOUT:\n{tail_out}\n"
            f"STDERR:\n{tail_err}\n\n"
            "Diagnose the failure and provide targeted code modifications to fix the errors."
        )
        rem_options = dict(original_request.options or {})
        rem_options["_preserve_journal"] = True
        return EngineRequest(
            request_id=f"{original_request.request_id}_remed_{attempt}",
            intent=RequestIntent.EDIT_CODE,
            prompt=prompt,
            context=original_request.context,
            adapter_name=original_request.adapter_name,
            options=rem_options,
            execution_policy=original_request.execution_policy,
        )

    def _attach_verification_metadata(
        self, response: EngineResponse, outcome: str
    ) -> EngineResponse:
        base_meta = response.execution_metadata or ExecutionMetadata()
        new_meta = ExecutionMetadata(
            analyzer_used=base_meta.analyzer_used,
            execution_mode_used=base_meta.execution_mode_used,
            sovereignty_outcome=base_meta.sovereignty_outcome,
            retrieval_summary=base_meta.retrieval_summary,
            trace_id=base_meta.trace_id,
            verification_outcome=outcome,
            degradations=base_meta.degradations,
            backend_warnings=base_meta.backend_warnings,
            routing_context=base_meta.routing_context,
        )
        return EngineResponse(
            request_id=response.request_id,
            content=response.content,
            model_used=response.model_used,
            usage=response.usage,
            artifacts=response.artifacts,
            error=response.error,
            execution_metadata=new_meta,
        )
