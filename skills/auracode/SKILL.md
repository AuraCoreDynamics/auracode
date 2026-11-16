---
name: auracode
description: >-
  Operate, configure, and manage AuraCode — the terminal-native, vendor-agnostic AI coding assistant.
  Use when running AuraCode CLI commands, CI/CD verification, bundle management, or cleanup.
---

# AuraCode: Terminal-Native AI Coding Assistant

**AuraCode** is a terminal-native, vendor-agnostic AI coding assistant powered by Federated Mixture-of-Experts (FMoE).

---

## 1. Zero-Configuration Bootstrappers (No `PYTHONPATH` Required)

Run directly from the source checkout on any OS without modifying `PYTHONPATH`:

```powershell
# Windows PowerShell
& ".\auracode.ps1" status
```

```bash
# Linux / macOS
./auracode.sh status
```

---

## 2. Common Agent Workflows

| Task | Command |
| :--- | :--- |
| **Check health & adapters** | `auracode.ps1 status` |
| **Launch interactive REPL** | `auracode.ps1 repl` (add `--allow-write`, `--allow-shell`, `--unsafe` as needed) |
| **Manage AuraGrid bundles** | `auracode.ps1 bundle --help` |
| **CI/CD verification & hooks** | `auracode.ps1 ci --help` |

---

## 3. State & Cleanup Locations

- **User state & audit logs**: `~/.auracode/` (`workspaces.json`, `audit/`, `ci_bypass.log`)
- **Clean uninstall**: `pip uninstall -y auracode` and remove `~/.auracode/`.

