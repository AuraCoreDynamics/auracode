# AuraCode IDE Integration & WebSocket Protocol V2

AuraCode delegates interactive buffer editing to native developer environments (Visual Studio 2022, VS Code, Spyder, JetBrains) while serving as the autonomous multi-agent reasoning, self-healing execution, and verification engine.

## Endpoint Overview

| Protocol | Endpoint | Description |
|:---|:---|:---|
| WebSocket | `ws://127.0.0.1:8741/ws/ide` | Bidirectional IDE protocol (V1 streaming chat + V2 self-healing & conflict resolution) |
| REST API | `http://127.0.0.1:8741/v1/chat/completions` | Standard OpenAI-compatible API shim |
| Mission Deck | `http://127.0.0.1:8741/ui` | Mission Command web cockpit for multi-project orchestration |

---

## IDE Wire Protocol V2

### 1. Autonomous Self-Healing (`ide.act_request`)
Invokes AuraCode's bounded 3-turn self-healing execution loop with transactional file journals and verification gates.

**Client Request (`ide.act_request`):**
```json
{
  "type": "ide.act_request",
  "prompt": "Fix null reference exception in UserController.cs",
  "verify_command": "dotnet test",
  "max_attempts": 3,
  "workspace": "."
}
```

**Server Stream (`ide.act_progress`):**
```json
{
  "type": "ide.act_progress",
  "status": "running",
  "phase": "planning",
  "attempt": 1
}
```

**Server Completion (`ide.act_completed`):**
```json
{
  "type": "ide.act_completed",
  "status": "PASSED",
  "snapshot_id": "snap-20261010-abc1234",
  "remediations_count": 1,
  "output": "Successfully fixed null check in UserController.cs and verified tests pass."
}
```

---

### 2. Merge Conflict Resolution (`ide.resolve_conflict_request`)
Invokes AuraCode's AI-powered 3-way merge conflict synthesizer.

**Client Request (`ide.resolve_conflict_request`):**
```json
{
  "type": "ide.resolve_conflict_request",
  "file_path": "src/App.cs",
  "workspace": "."
}
```

**Server Response (`ide.resolve_conflict_response`):**
```json
{
  "type": "ide.resolve_conflict_response",
  "file_path": "src/App.cs",
  "success": true,
  "message": "Resolved 2 merge conflict blocks."
}
```

---

### 3. Structural AST Repo-Map (`ide.repomap_request`)
Retrieves a deterministic structural outline of classes, functions, and symbols (<2KB) without needing vector databases.

**Client Request (`ide.repomap_request`):**
```json
{
  "type": "ide.repomap_request",
  "workspace_root": ".",
  "max_chars": 2048
}
```

**Server Response (`ide.repomap_response`):**
```json
{
  "type": "ide.repomap_response",
  "workspace_root": ".",
  "map_text": "class Service:\n    def execute(self):\n...",
  "symbol_count": 42
}
```

---

## Spyder & Scientific Python Bridge

For Python data science and scientific workflows in Spyder:

```python
from auracode.adapters.spyder_bridge import SpyderAuraCodeBridge

bridge = SpyderAuraCodeBridge()

# Open Mission Command operations deck
bridge.launch_ui()

# Inspect deterministic AST outline
outline = bridge.get_repo_map()
print(outline)

# Run interactive verification
result = bridge.verify("pytest tests/")
print(f"Passed: {result['passed']} (Exit {result['exit_code']})")
```
