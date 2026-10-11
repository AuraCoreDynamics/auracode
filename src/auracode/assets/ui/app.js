/**
 * AuraCode Mission Command Flight Deck Controller
 * Vanilla JavaScript WebSocket & REST Telemetry Manager
 */

(function () {
  "use strict";

  // State Management
  const state = {
    workspaces: [],
    activeWorkspace: ".",
    conflicts: [],
    selectedConflictFile: null,
    events: [],
    ws: null,
    wsReconnectAttempts: 0,
    reconnectTimer: null,
  };

  // DOM Elements
  const elements = {
    wsIndicator: document.getElementById("ws-indicator"),
    wsStatusText: document.getElementById("ws-status-text"),
    selectActiveWorkspace: document.getElementById("select-active-workspace"),
    navTabs: document.querySelectorAll(".nav-tab"),
    deckSections: document.querySelectorAll(".deck-section"),
    // Fleet
    statWorkspaces: document.getElementById("stat-workspace-count"),
    statBranches: document.getElementById("stat-branch-count"),
    statDirty: document.getElementById("stat-dirty-count"),
    statConflicts: document.getElementById("stat-conflict-count"),
    fleetCardGrid: document.getElementById("fleet-card-grid"),
    badgeFleetCount: document.getElementById("badge-fleet-count"),
    btnRefreshFleet: document.getElementById("btn-refresh-fleet"),
    btnAddWorkspace: document.getElementById("btn-add-workspace"),
    modalRegisterWorkspace: document.getElementById("modal-register-workspace"),
    inputWorkspacePath: document.getElementById("input-workspace-path"),
    btnCancelModal: document.getElementById("btn-cancel-modal"),
    btnConfirmRegister: document.getElementById("btn-confirm-register"),
    // Verification
    badgeVerifStatus: document.getElementById("badge-verif-status"),
    stepPlan: document.getElementById("step-plan"),
    stepEdit: document.getElementById("step-edit"),
    stepVerify: document.getElementById("step-verify"),
    stepRemediate: document.getElementById("step-remediate"),
    consoleCmdBadge: document.getElementById("console-cmd-badge"),
    consoleOutput: document.getElementById("verification-console-output"),
    btnRollback: document.getElementById("btn-rollback"),
    // Conflicts
    badgeConflictCount: document.getElementById("badge-conflict-count"),
    conflictFileList: document.getElementById("conflict-file-list"),
    diffOurs: document.getElementById("diff-ours-content"),
    diffTheirs: document.getElementById("diff-theirs-content"),
    diffResolution: document.getElementById("diff-resolution-content"),
    labelOursBranch: document.getElementById("label-ours-branch"),
    labelTheirsBranch: document.getElementById("label-theirs-branch"),
    btnScanConflicts: document.getElementById("btn-scan-conflicts"),
    btnResolveSelected: document.getElementById("btn-resolve-selected-file"),
    btnResolveAll: document.getElementById("btn-resolve-all-conflicts"),
    // Stream
    streamFeed: document.getElementById("stream-event-feed"),
    badgeStreamCount: document.getElementById("badge-stream-count"),
    eventCounter: document.getElementById("terminal-event-counter"),
    btnClearStream: document.getElementById("btn-clear-stream"),
    toastContainer: document.getElementById("toast-container"),
  };


  // --- Initialize Application ---
  function init() {
    setupTabNavigation();
    setupEventListeners();
    connectWebSocket();
    loadFleetWorkspaces();
    loadConflicts();
    setInterval(loadFleetWorkspaces, 15000);
  }


  // --- Tab Navigation ---
  function setupTabNavigation() {
    elements.navTabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        elements.navTabs.forEach(function (t) {
          t.classList.remove("active");
          t.setAttribute("aria-selected", "false");
        });
        elements.deckSections.forEach(function (s) {
          s.classList.remove("active");
        });

        tab.classList.add("active");
        tab.setAttribute("aria-selected", "true");
        var targetDeckId = tab.getAttribute("data-deck");
        var targetDeck = document.getElementById(targetDeckId);
        if (targetDeck) {
          targetDeck.classList.add("active");
        }
      });
    });
  }

  // --- WebSocket Telemetry Stream ---
  function connectWebSocket() {
    if (state.ws) {
      state.ws.close();
    }

    var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    var wsUrl = protocol + "//" + window.location.host + "/api/events";

    updateWsStatus(false, "CONNECTING");
    try {
      state.ws = new WebSocket(wsUrl);
    } catch (err) {
      handleWsDisconnect();
      return;
    }

    state.ws.onopen = function () {
      state.wsReconnectAttempts = 0;
      updateWsStatus(true, "CONNECTED");
      showToast("Mission Event Bus Connected", "success");
    };

    state.ws.onmessage = function (event) {
      try {
        var data = JSON.parse(event.data);
        handleIncomingEvent(data);
      } catch (e) {
        console.warn("Failed to parse event:", event.data);
      }
    };

    state.ws.onclose = function () {
      handleWsDisconnect();
    };

    state.ws.onerror = function () {
      state.ws.close();
    };
  }

  function handleWsDisconnect() {
    updateWsStatus(false, "DISCONNECTED");
    var delay = Math.min(10000, 1000 * Math.pow(1.5, state.wsReconnectAttempts++));
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = setTimeout(connectWebSocket, delay);
  }

  function updateWsStatus(online, text) {
    if (online) {
      elements.wsIndicator.className = "status-dot dot-online";
    } else {
      elements.wsIndicator.className = "status-dot dot-offline";
    }
    elements.wsStatusText.textContent = text;
  }

  // --- Incoming Event Router ---
  function handleIncomingEvent(evt) {
    state.events.push(evt);
    if (state.events.length > 200) {
      state.events.shift();
    }

    // Update Counter
    elements.badgeStreamCount.textContent = state.events.length;
    elements.eventCounter.textContent = state.events.length + " events buffered";

    // Append to Terminal Feed
    appendEventToTerminal(evt);

    // Route event actions
    var type = evt.type || "";
    var payload = evt.payload || {};

    if (type.indexOf("verification.") === 0) {
      handleVerificationEvent(type, payload);
    } else if (type.indexOf("git.conflict") === 0) {
      loadConflicts();
    } else if (type === "git.mirror_polled") {
      loadFleetWorkspaces();
      showToast("Git push detected: " + (payload.repo || "repo"), "info");
    } else if (type === "journal.rollback_executed") {
      showToast("Snapshot rolled back: " + payload.restored_count + " files restored", "success");
    }
  }

  function appendEventToTerminal(evt) {
    var entry = document.createElement("div");
    entry.className = "event-entry";

    var timeStr = new Date((evt.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString();
    var timeSpan = document.createElement("span");
    timeSpan.className = "event-time";
    timeSpan.textContent = "[" + timeStr + "]";

    var tagSpan = document.createElement("span");
    var type = evt.type || "system";
    var tagClass = "tag-agent";
    if (type.indexOf("verification") >= 0) tagClass = "tag-verification";
    else if (type.indexOf("git") >= 0) tagClass = "tag-git";
    else if (type.indexOf("journal") >= 0) tagClass = "tag-journal";
    else if (type.indexOf("error") >= 0) tagClass = "tag-error";

    tagSpan.className = "event-tag " + tagClass;
    tagSpan.textContent = type;

    var msgSpan = document.createElement("span");
    msgSpan.className = "event-msg";
    msgSpan.textContent = JSON.stringify(evt.payload || {});

    entry.appendChild(timeSpan);
    entry.appendChild(tagSpan);
    entry.appendChild(msgSpan);

    elements.streamFeed.appendChild(entry);
    elements.streamFeed.scrollTop = elements.streamFeed.scrollHeight;
  }

  function handleVerificationEvent(type, payload) {
    if (type === "verification.executed") {
      elements.badgeVerifStatus.textContent = "RUNNING";
      elements.badgeVerifStatus.className = "tab-badge badge-warning";
      elements.consoleCmdBadge.textContent = payload.command || "TEST RUN";
      elements.stepVerify.className = "pipeline-step step-active";
      elements.consoleOutput.textContent = "// Executing verification command: " + payload.command + "...\n";
    } else if (type === "verification.result") {
      if (payload.passed) {
        elements.badgeVerifStatus.textContent = "PASSED";
        elements.badgeVerifStatus.className = "tab-badge badge-cyan";
        elements.stepVerify.className = "pipeline-step step-complete";
        elements.consoleOutput.textContent += "\n[VERIFICATION PASSED] Exit code 0\n";
        showToast("Verification Gate Passed", "success");
      } else {
        elements.badgeVerifStatus.textContent = "REMEDIATING";
        elements.badgeVerifStatus.className = "tab-badge badge-warning";
        elements.stepVerify.className = "pipeline-step";
        elements.stepRemediate.className = "pipeline-step step-active";
        elements.consoleOutput.textContent += "\n[VERIFICATION FAILED] Exit code " + payload.returncode + "\nInitiating self-healing loop turn...\n";
        showToast("Verification Gate Failed — Self-Healing...", "warning");
      }
    }
  }

  // --- REST Operations ---
  async function loadFleetWorkspaces() {
    try {
      var res = await fetch("/api/fleet/workspaces");
      if (!res.ok) return;
      var data = await res.json();
      state.workspaces = data.workspaces || [];
      renderFleetGrid(state.workspaces);
      updateWorkspaceSelector(state.workspaces);
    } catch (err) {
      console.error("Failed to load fleet workspaces:", err);
    }
  }

  function updateWorkspaceSelector(workspaces) {
    if (!elements.selectActiveWorkspace) return;
    var current = state.activeWorkspace;
    elements.selectActiveWorkspace.innerHTML = "";
    workspaces.forEach(function (ws) {
      var opt = document.createElement("option");
      opt.value = ws.path;
      opt.textContent = ws.name + " (" + ws.branch + ")";
      if (ws.path === current || (current === "." && ws.name === ".")) {
        opt.selected = true;
      }
      elements.selectActiveWorkspace.appendChild(opt);
    });
  }

  function renderFleetGrid(workspaces) {
    elements.fleetCardGrid.innerHTML = "";
    elements.statWorkspaces.textContent = workspaces.length;
    elements.badgeFleetCount.textContent = workspaces.length;

    var dirtyCount = 0;
    var totalConflicts = 0;
    var branches = new Set();

    if (workspaces.length === 0) {
      elements.fleetCardGrid.innerHTML =
        '<div class="glass-card placeholder-card"><p>No workspaces currently active.</p></div>';
      return;
    }

    workspaces.forEach(function (ws) {
      if (ws.dirty) dirtyCount++;
      if (ws.conflict_count) totalConflicts += ws.conflict_count;
      if (ws.branch) branches.add(ws.branch);

      var card = document.createElement("div");
      card.className = "glass-card fleet-card";

      card.innerHTML =
        '<div class="fleet-card-header">' +
          '<span class="fleet-repo-name">' + escapeHtml(ws.name) + '</span>' +
          '<span class="badge badge-cyan">' + escapeHtml(ws.branch) + '</span>' +
        '</div>' +
        '<div class="fleet-meta-list">' +
          '<div class="fleet-meta-row">' +
            '<span>Working Tree:</span>' +
            '<span class="fleet-meta-val ' + (ws.dirty ? 'text-amber' : 'text-emerald') + '">' +
              (ws.dirty ? 'DIRTY / MODIFIED' : 'CLEAN') +
            '</span>' +
          '</div>' +
          '<div class="fleet-meta-row">' +
            '<span>Conflicts:</span>' +
            '<span class="fleet-meta-val ' + (ws.conflict_count > 0 ? 'text-crimson' : 'text-emerald') + '">' +
              ws.conflict_count + ' detected' +
            '</span>' +
          '</div>' +
          '<div class="fleet-meta-row">' +
            '<span>Agent Status:</span>' +
            '<span class="fleet-meta-val text-cyan">Autonomous Orchestrator Ready</span>' +
          '</div>' +
        '</div>' +
        '<div style="margin-top:0.75rem; display:flex; gap:0.5rem; justify-content:space-between; align-items:center;">' +
          '<div style="display:flex; gap:0.4rem;">' +
            '<button class="btn btn-secondary btn-select-ws" data-path="' + escapeHtml(ws.path) + '">Select</button>' +
            '<button class="btn btn-secondary btn-poll-repo" data-repo="' + escapeHtml(ws.name) + '">&#8635; Poll Sync</button>' +
          '</div>' +
          '<button class="btn-card-danger btn-remove-ws" data-path="' + escapeHtml(ws.path) + '">Unregister</button>' +
        '</div>';

      elements.fleetCardGrid.appendChild(card);
    });

    elements.fleetCardGrid.querySelectorAll(".btn-select-ws").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var p = btn.getAttribute("data-path");
        state.activeWorkspace = p;
        if (elements.selectActiveWorkspace) {
          elements.selectActiveWorkspace.value = p;
        }
        loadConflicts();
        showToast("Switched active workspace to " + p, "info");
      });
    });

    elements.fleetCardGrid.querySelectorAll(".btn-remove-ws").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var p = btn.getAttribute("data-path");
        try {
          var res = await fetch("/api/fleet/workspaces", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: p }),
          });
          if (res.ok) {
            showToast("Unregistered workspace: " + p, "info");
            loadFleetWorkspaces();
          }
        } catch (e) {
          showToast("Failed to unregister workspace", "error");
        }
      });
    });

    elements.statDirty.textContent = dirtyCount;
    elements.statConflictCount.textContent = totalConflicts;
    elements.statBranches.textContent = Array.from(branches).join(", ") || "-";
  }

  async function loadConflicts() {
    try {
      var targetWs = state.activeWorkspace || ".";
      var res = await fetch("/api/fleet/conflicts?workspace=" + encodeURIComponent(targetWs));
      if (!res.ok) return;

      var data = await res.json();
      state.conflicts = data.conflicts || [];
      renderConflicts(state.conflicts);
    } catch (err) {
      console.error("Failed to load conflicts:", err);
    }
  }

  function renderConflicts(conflicts) {
    elements.conflictFileList.innerHTML = "";
    elements.badgeConflictCount.textContent = conflicts.length;
    elements.statConflictCount.textContent = conflicts.length;

    if (conflicts.length === 0) {
      elements.conflictFileList.innerHTML =
        '<li class="empty-state">No active Git conflict markers detected.</li>';
      elements.diffOurs.textContent = "// Clean workspace: zero merge conflicts.";
      elements.diffTheirs.textContent = "// Clean workspace: zero merge conflicts.";
      elements.diffResolution.textContent = "// No resolution required.";
      state.selectedConflictFile = null;
      return;
    }

    conflicts.forEach(function (c, idx) {
      var li = document.createElement("li");
      li.className = "file-item" + (idx === 0 ? " selected" : "");
      li.innerHTML =
        '<span>' + escapeHtml(c.relative_file || c.file) + '</span>' +
        '<span class="badge badge-warning">' + c.block_count + ' blocks</span>';

      li.addEventListener("click", function () {
        document.querySelectorAll(".file-item").forEach(function (el) {
          el.classList.remove("selected");
        });
        li.classList.add("selected");
        selectConflictFile(c);
      });

      elements.conflictFileList.appendChild(li);
    });

    selectConflictFile(conflicts[0]);
  }

  function selectConflictFile(conflictObj) {
    state.selectedConflictFile = conflictObj;
    if (!conflictObj || !conflictObj.blocks || conflictObj.blocks.length === 0) return;

    var b = conflictObj.blocks[0];
    elements.labelOursBranch.textContent = b.ours_label || "HEAD";
    elements.labelTheirsBranch.textContent = b.theirs_label || "REMOTE";
    elements.diffOurs.textContent = b.ours_content || "";
    elements.diffTheirs.textContent = b.theirs_content || "";
    elements.diffResolution.textContent =
      "// Ready to reconcile " + conflictObj.block_count + " block(s).\n" +
      "// Click 'Approve & Stage Resolution' to synthesize clean code.";
  }

  async function resolveSelectedConflict() {
    if (!state.selectedConflictFile) {
      showToast("No conflicted file selected", "warning");
      return;
    }

    var targetPath = state.selectedConflictFile.file;
    showToast("Synthesizing merge resolution for " + (state.selectedConflictFile.relative_file || targetPath) + "...", "info");

    try {
      var res = await fetch("/api/fleet/conflicts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file: targetPath }),
      });
      var data = await res.json();
      if (data.success) {
        showToast(data.message || "Conflict resolved successfully", "success");
        await loadConflicts();
      } else {
        showToast("Conflict resolution failed: " + (data.message || "Unknown error"), "error");
      }
    } catch (err) {
      showToast("Error invoking conflict resolver: " + err, "error");
    }
  }

  async function resolveAllConflicts() {
    showToast("Synthesizing merge resolution for all conflicted files...", "info");
    try {
      var res = await fetch("/api/fleet/conflicts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ all: true }),
      });
      var data = await res.json();
      if (data.success) {
        showToast("Resolved " + data.resolved_count + " files cleanly", "success");
        await loadConflicts();
      } else {
        showToast("Conflict resolution encountered issues", "error");
      }
    } catch (err) {
      showToast("Error invoking resolver: " + err, "error");
    }
  }

  async function triggerRollback() {
    if (!confirm("Roll back filesystem changes to the pre-run snapshot checkpoint?")) {
      return;
    }

    try {
      var res = await fetch("/api/fleet/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      var data = await res.json();
      if (data.success) {
        showToast("Snapshot Rollback Complete: " + data.restored_count + " files reverted", "success");
        await loadFleetWorkspaces();
      } else {
        showToast("Rollback failed: " + (data.message || "Unknown"), "error");
      }
    } catch (err) {
      showToast("Error triggering rollback: " + err, "error");
    }
  }

  // --- Event Listeners Setup ---
  function setupEventListeners() {
    elements.btnRefreshFleet.addEventListener("click", function () {
      loadFleetWorkspaces();
      showToast("Fleet workspaces refreshed", "info");
    });

    elements.btnRollback.addEventListener("click", triggerRollback);
    elements.btnScanConflicts.addEventListener("click", loadConflicts);
    elements.btnResolveSelected.addEventListener("click", resolveSelectedConflict);
    elements.btnResolveAll.addEventListener("click", resolveAllConflicts);

    if (elements.selectActiveWorkspace) {
      elements.selectActiveWorkspace.addEventListener("change", function () {
        state.activeWorkspace = elements.selectActiveWorkspace.value;
        loadConflicts();
        showToast("Active workspace: " + state.activeWorkspace, "info");
      });
    }

    if (elements.btnAddWorkspace && elements.modalRegisterWorkspace) {
      elements.btnAddWorkspace.addEventListener("click", function () {
        elements.modalRegisterWorkspace.showModal();
        if (elements.inputWorkspacePath) {
          elements.inputWorkspacePath.value = "";
          elements.inputWorkspacePath.focus();
        }
      });
    }

    if (elements.btnCancelModal && elements.modalRegisterWorkspace) {
      elements.btnCancelModal.addEventListener("click", function () {
        elements.modalRegisterWorkspace.close();
      });
    }

    if (elements.btnConfirmRegister && elements.modalRegisterWorkspace) {
      elements.btnConfirmRegister.addEventListener("click", async function () {
        var val = elements.inputWorkspacePath ? elements.inputWorkspacePath.value.trim() : "";
        if (!val) {
          showToast("Please enter a valid path", "error");
          return;
        }
        try {
          var res = await fetch("/api/fleet/workspaces", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: val }),
          });
          var data = await res.json();
          if (res.ok && data.success) {
            elements.modalRegisterWorkspace.close();
            showToast("Registered workspace successfully", "success");
            loadFleetWorkspaces();
          } else {
            showToast(data.error || "Failed to register workspace", "error");
          }
        } catch (e) {
          showToast("Network error registering workspace", "error");
        }
      });
    }

    elements.btnClearStream.addEventListener("click", function () {
      elements.streamFeed.innerHTML = "";
      state.events = [];
      elements.badgeStreamCount.textContent = "0";
      elements.eventCounter.textContent = "0 events buffered";
    });
  }


  // --- UI Toast Helpers ---
  function showToast(msg, type) {
    var toast = document.createElement("div");
    toast.className = "toast toast-" + (type || "info");
    toast.textContent = msg;
    elements.toastContainer.appendChild(toast);

    setTimeout(function () {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(20px)";
      toast.style.transition = "all 0.25s ease";
      setTimeout(function () {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 250);
    }, 3500);
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }

  // Boot on DOM Ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
