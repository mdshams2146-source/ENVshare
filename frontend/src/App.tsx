import React, { useState, useEffect, useRef, useCallback } from "react";
import { api } from "./api";
import type {
  User,
  Project,
  Environment,
  VariableItem,
  DiffItem,
  HistoryItem,
  SnapshotItem,
  ProjectMemberItem
} from "./types";
import {
  KeyRound, Shield, Eye, EyeOff, Plus, Trash2, ClipboardPaste,
  History, LogOut, CheckCircle, AlertTriangle, ArrowRight, UserPlus, FolderPlus, Download,
  Copy, Check, RotateCcw, Camera, RefreshCw, Users, X, Pencil
} from "lucide-react";

function getErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === "object" && "response" in err) {
    const res = (err as { response?: { data?: { detail?: string } | string } }).response;
    if (res?.data) {
      if (typeof res.data === "string") return res.data;
      if (typeof res.data.detail === "string") return res.data.detail;
      if (Array.isArray(res.data.detail)) {
        return (res.data.detail as Array<{ msg?: string }>)
          .map((d) => d.msg || JSON.stringify(d))
          .join(", ");
      }
      return JSON.stringify(res.data);
    }
  }
  if (err instanceof Error) {
    return err.message;
  }
  return fallback;
}

export default function App() {
  const inviteProcessedRef = useRef(false);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [revertingLogId, setRevertingLogId] = useState<string | null>(null);

  // Snapshot Disaster Recovery States
  const [showSnapshotsModal, setShowSnapshotsModal] = useState(false);
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);
  const [newSnapshotName, setNewSnapshotName] = useState("");
  const [isRollingBack, setIsRollingBack] = useState<string | null>(null);

  // Members Modal State (UI-06)
  const [showMembersModal, setShowMembersModal] = useState(false);
  const [projectMembers, setProjectMembers] = useState<ProjectMemberItem[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);

  // Invitation Feedback State (INV-02, FE-02)
  const [inviteFeedback, setInviteFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Preserve invite token across registration / login flow
  const [pendingInviteToken, setPendingInviteToken] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search || window.location.hash.replace(/^#/, "?"));
    const fromUrl = params.get("invite");
    if (fromUrl) {
      sessionStorage.setItem("envshare_pending_invite", fromUrl);
      return fromUrl;
    }
    return sessionStorage.getItem("envshare_pending_invite");
  });

  // Auth view states - lazy initialization from query/hash to avoid setState in effect (CODE-04)
  const [resetToken, setResetToken] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search || window.location.hash.replace(/^#/, "?"));
    return params.get("reset_token");
  });
  const [authMode, setAuthMode] = useState<"login" | "register" | "forgot" | "reset">(() => {
    const params = new URLSearchParams(window.location.search || window.location.hash.replace(/^#/, "?"));
    if (params.get("reset_token")) return "reset";
    if (params.get("invite") || sessionStorage.getItem("envshare_pending_invite")) return "register";
    return "login";
  });
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authName, setAuthName] = useState("");
  const [authError, setAuthError] = useState("");
  const [authSuccessMsg, setAuthSuccessMsg] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [authLoading, setAuthLoading] = useState(false);

  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [activeEnv, setActiveEnv] = useState<Environment | null>(null);
  const [variables, setVariables] = useState<VariableItem[]>([]);
  const [revealedKeys, setRevealedKeys] = useState<{ [id: string]: string }>({});

  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");

  const [showAddVarModal, setShowAddVarModal] = useState(false);
  const [newVarKey, setNewVarKey] = useState("");
  const [newVarVal, setNewVarVal] = useState("");
  const [newVarSensitive, setNewVarSensitive] = useState(false);

  // Variable Edit State
  const [editingVariable, setEditingVariable] = useState<VariableItem | null>(null);
  const [editVarValue, setEditVarValue] = useState("");
  const [editVarSensitive, setEditVarSensitive] = useState(false);
  const [editVarLoading, setEditVarLoading] = useState(false);
  const [editVarFetching, setEditVarFetching] = useState(false);
  const [editVarError, setEditVarError] = useState<string | null>(null);

  // In-App Direct Invite State
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteUrl, setInviteUrl] = useState("");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [copiedInvite, setCopiedInvite] = useState(false);

  const [showBulkModal, setShowBulkModal] = useState(false);
  const [rawEnvText, setRawEnvText] = useState("");
  const [diffItems, setDiffItems] = useState<DiffItem[] | null>(null);

  const [viewHistory, setViewHistory] = useState(false);
  const [historyLogs, setHistoryLogs] = useState<HistoryItem[]>([]);

  // Function declarations before useEffect hooks (CODE-01)
  const loadProjects = useCallback(async (preferredProjectId?: string) => {
    try {
      const res = await api.get<Project[]>("/projects");
      setProjects(res.data);
      if (res.data.length > 0) {
        setActiveProject((current) => {
          if (preferredProjectId) {
            const preferred = res.data.find((p) => p.id === preferredProjectId);
            if (preferred) return preferred;
          }
          if (current) {
            const updated = res.data.find((p) => p.id === current.id);
            return updated || res.data[0];
          }
          return res.data[0];
        });
        setActiveEnv((currentEnv) => {
          if (preferredProjectId) {
            const targetProj = res.data.find((p) => p.id === preferredProjectId);
            if (targetProj && targetProj.environments.length > 0) {
              return targetProj.environments[0];
            }
          }
          if (currentEnv) return currentEnv;
          return res.data[0].environments[0] || null;
        });
      }
    } catch (err: unknown) {
      console.error(err);
    }
  }, []);

  const loadVariables = useCallback(async () => {
    if (!activeEnv) return;
    try {
      const res = await api.get<VariableItem[]>(`/environments/${activeEnv.id}/variables`);
      setVariables(res.data);
      setRevealedKeys({});
    } catch (err: unknown) {
      console.error(err);
    }
  }, [activeEnv]);

  const loadHistory = useCallback(async () => {
    if (!activeEnv) return;
    try {
      const res = await api.get<HistoryItem[]>(`/environments/${activeEnv.id}/history`);
      setHistoryLogs(res.data);
    } catch (err: unknown) {
      console.error(err);
    }
  }, [activeEnv]);

  const loadSnapshots = useCallback(async () => {
    if (!activeEnv) return;
    try {
      const res = await api.get<SnapshotItem[]>(`/environments/${activeEnv.id}/snapshots`);
      setSnapshots(res.data);
    } catch (err: unknown) {
      console.error("Failed to load snapshots", err);
    }
  }, [activeEnv]);

  const loadMembers = useCallback(async () => {
    if (!activeProject) return;
    setLoadingMembers(true);
    try {
      const res = await api.get<ProjectMemberItem[]>(`/projects/${activeProject.id}/members`);
      setProjectMembers(res.data);
    } catch (err: unknown) {
      console.error("Failed to load members", err);
    } finally {
      setLoadingMembers(false);
    }
  }, [activeProject]);

  // Clean URL parameters once read
  useEffect(() => {
    if (window.location.search.includes("reset_token") || window.location.hash.includes("reset_token")) {
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  // 1. Auto-reload project data when authenticated after browser refresh (FE-01)
  useEffect(() => {
    if (!token) return;
    let isMounted = true;

    api.get<Project[]>("/projects")
      .then((res) => {
        if (!isMounted) return;
        setProjects(res.data);
        if (res.data.length > 0) {
          setActiveProject((current) => current || res.data[0]);
          if (res.data[0].environments.length > 0) {
            setActiveEnv((currentEnv) => currentEnv || res.data[0].environments[0]);
          }
        }
      })
      .catch((err: unknown) => {
        console.error("Failed to load initial projects", err);
      });

    return () => {
      isMounted = false;
    };
  }, [token]);

  // 2. Detect & accept project invite link once authenticated (INV-01, INV-02, FE-02)
  useEffect(() => {
    if (!token) return;

    const params = new URLSearchParams(window.location.search || window.location.hash.replace(/^#/, "?"));
    const inviteParam = params.get("invite") || sessionStorage.getItem("envshare_pending_invite");

    if (inviteParam && !inviteProcessedRef.current) {
      inviteProcessedRef.current = true;

      api.post("/projects/accept-invite", { token: inviteParam })
        .then((res) => {
          sessionStorage.removeItem("envshare_pending_invite");
          setPendingInviteToken(null);
          setInviteFeedback({
            type: "success",
            message: res.data?.message || "Successfully joined project!"
          });
          window.history.replaceState({}, document.title, window.location.pathname);
          loadProjects(res.data?.project_id);
        })
        .catch((err: unknown) => {
          sessionStorage.removeItem("envshare_pending_invite");
          setPendingInviteToken(null);
          const detail = getErrorMessage(err, "Invalid or expired invitation link");
          setInviteFeedback({ type: "error", message: detail });
          console.warn("Invite note:", detail);
          window.history.replaceState({}, document.title, window.location.pathname);
          loadProjects();
        });
    }
  }, [token, loadProjects]);

  // 3. Load variables and history when active environment changes
  useEffect(() => {
    if (!activeEnv) return;
    let isMounted = true;

    api.get<VariableItem[]>(`/environments/${activeEnv.id}/variables`)
      .then((res) => {
        if (!isMounted) return;
        setVariables(res.data);
        setRevealedKeys({});
      })
      .catch((err: unknown) => {
        console.error("Failed to fetch variables", err);
      });

    if (viewHistory) {
      api.get<HistoryItem[]>(`/environments/${activeEnv.id}/history`)
        .then((res) => {
          if (!isMounted) return;
          setHistoryLogs(res.data);
        })
        .catch((err: unknown) => {
          console.error("Failed to fetch history", err);
        });
    }

    return () => {
      isMounted = false;
    };
  }, [activeEnv, viewHistory]);

  // Handle Login and Register
  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    setAuthSuccessMsg("");
    setAuthLoading(true);
    try {
      const endpoint = authMode === "login" ? "/auth/login" : "/auth/register";
      const payload = authMode === "login"
        ? { email: authEmail, password: authPassword }
        : { name: authName, email: authEmail, password: authPassword };

      const res = await api.post(endpoint, payload);
      localStorage.setItem("token", res.data.access_token);
      setToken(res.data.access_token);
      setCurrentUser(res.data.user);

      // Claim pending invite token immediately with new credentials
      const pendingInvite = sessionStorage.getItem("envshare_pending_invite") || new URLSearchParams(window.location.search).get("invite");
      if (pendingInvite) {
        inviteProcessedRef.current = true;
        try {
          const inviteRes = await api.post("/projects/accept-invite", { token: pendingInvite }, {
            headers: { Authorization: `Bearer ${res.data.access_token}` }
          });
          sessionStorage.removeItem("envshare_pending_invite");
          setPendingInviteToken(null);
          window.history.replaceState({}, document.title, window.location.pathname);
          setInviteFeedback({
            type: "success",
            message: inviteRes.data?.message || "Successfully joined project as Collaborator!"
          });
          await loadProjects(inviteRes.data?.project_id);
        } catch (inviteErr: unknown) {
          sessionStorage.removeItem("envshare_pending_invite");
          setPendingInviteToken(null);
          window.history.replaceState({}, document.title, window.location.pathname);
          setInviteFeedback({
            type: "error",
            message: getErrorMessage(inviteErr, "Invalid or expired invitation link")
          });
          await loadProjects();
        }
      } else {
        await loadProjects();
      }
    } catch (err: unknown) {
      const msg = getErrorMessage(err, "Authentication failed");
      setAuthError(msg);
    } finally {
      setAuthLoading(false);
    }
  };

  // Handle Requesting Password Reset Link
  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    setAuthSuccessMsg("");
    setAuthLoading(true);
    try {
      const res = await api.post("/auth/forgot-password", { email: authEmail });
      setAuthSuccessMsg(res.data.message || "Reset link sent! Please check your inbox.");
    } catch (err: unknown) {
      setAuthError(getErrorMessage(err, "Failed to send reset link. Try again later."));
    } finally {
      setAuthLoading(false);
    }
  };

  // Handle Submitting New Password
  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    setAuthSuccessMsg("");

    if (newPassword.length < 8) {
      setAuthError("Password must be at least 8 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setAuthError("Passwords do not match.");
      return;
    }

    setAuthLoading(true);
    try {
      const res = await api.post("/auth/reset-password", {
        token: resetToken,
        new_password: newPassword,
      });
      setAuthSuccessMsg(res.data.message || "Password updated successfully!");
      window.history.replaceState({}, document.title, window.location.pathname);
      setTimeout(() => {
        setAuthMode("login");
        setAuthSuccessMsg("Password reset complete. Please log in with your new credentials.");
        setNewPassword("");
        setConfirmPassword("");
        setResetToken(null);
      }, 2000);
    } catch (err: unknown) {
      setAuthError(getErrorMessage(err, "Invalid or expired reset token."));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setCurrentUser(null);
    setAuthEmail("");
    setAuthPassword("");
    setAuthError("");
    setAuthSuccessMsg("");
    setProjects([]);
    setActiveProject(null);
    setActiveEnv(null);
    setInviteFeedback(null);
  };

  const createProject = async () => {
    if (!newProjectName.trim()) return;
    try {
      const res = await api.post("/projects", {
        name: newProjectName.trim(),
        description: newProjectDesc.trim() || undefined
      });
      setShowNewProjectModal(false);
      setNewProjectName("");
      setNewProjectDesc("");
      loadProjects();
      setActiveProject(res.data);
      if (res.data.environments && res.data.environments.length > 0) {
        setActiveEnv(res.data.environments[0]);
      }
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Error creating project"));
    }
  };

  const generateInviteLink = async () => {
    if (!activeProject) return;
    setInviteLoading(true);
    try {
      const res = await api.post(`/projects/${activeProject.id}/invites`);
      setInviteUrl(res.data.invite_url);
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to generate invite link"));
    } finally {
      setInviteLoading(false);
    }
  };

  const handleCopyInviteLink = () => {
    if (!inviteUrl) return;
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(inviteUrl)
        .then(() => {
          setCopiedInvite(true);
          setTimeout(() => setCopiedInvite(false), 2000);
        })
        .catch(() => {
          alert("Could not copy automatically. Please select and copy the link manually.");
        });
    } else {
      alert("Clipboard API not available. Please copy the link manually.");
    }
  };

  const handleCreateSnapshot = async () => {
    if (!activeEnv) return;
    try {
      await api.post(`/environments/${activeEnv.id}/snapshots`, {
        name: newSnapshotName.trim() || `Snapshot ${new Date().toLocaleTimeString()}`
      });
      setNewSnapshotName("");
      loadSnapshots();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to create snapshot"));
    }
  };

  const handleRollbackSnapshot = async (snap: SnapshotItem) => {
    if (!activeEnv) return;
    if (!confirm(`Warning: Rolling back to "${snap.name}" will replace all current environment variables. A safety backup of your current state will be saved. Continue?`)) {
      return;
    }

    setIsRollingBack(snap.id);
    try {
      await api.post(`/environments/${activeEnv.id}/snapshots/${snap.id}/rollback`);
      await loadVariables();
      await loadSnapshots();
      alert(`Successfully restored environment to "${snap.name}"!`);
      setShowSnapshotsModal(false);
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Rollback failed"));
    } finally {
      setIsRollingBack(null);
    }
  };

  const addVariable = async () => {
    if (!activeEnv || !newVarKey.trim()) return;
    try {
      await api.post(`/environments/${activeEnv.id}/variables`, {
        key: newVarKey.trim(),
        value: newVarVal,
        is_sensitive: newVarSensitive
      });
      setShowAddVarModal(false);
      setNewVarKey("");
      setNewVarVal("");
      setNewVarSensitive(false);
      loadVariables();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to add variable"));
    }
  };

  const deleteVariable = async (varId: string) => {
    if (!activeEnv || !confirm("Are you sure you want to delete this variable?")) return;
    try {
      await api.delete(`/environments/${activeEnv.id}/variables/${varId}`);
      loadVariables();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Delete failed"));
    }
  };

  const openEditVariableModal = async (v: VariableItem) => {
    setEditingVariable(v);
    setEditVarSensitive(v.is_sensitive);
    setEditVarError(null);
    if (v.is_sensitive) {
      if (revealedKeys[v.id] !== undefined) {
        setEditVarValue(revealedKeys[v.id]);
      } else if (activeEnv) {
        setEditVarFetching(true);
        try {
          const res = await api.post(`/environments/${activeEnv.id}/variables/${v.id}/reveal`);
          setEditVarValue(res.data.value);
          setRevealedKeys((prev) => ({ ...prev, [v.id]: res.data.value }));
        } catch {
          setEditVarValue("");
        } finally {
          setEditVarFetching(false);
        }
      }
    } else {
      setEditVarValue(v.value);
    }
  };

  const handleSaveEditVariable = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeEnv || !editingVariable) return;
    setEditVarLoading(true);
    setEditVarError(null);
    try {
      await api.put<VariableItem>(
        `/environments/${activeEnv.id}/variables/${editingVariable.id}`,
        {
          value: editVarValue,
          is_sensitive: editVarSensitive
        }
      );
      if (editVarSensitive) {
        setRevealedKeys((prev) => ({ ...prev, [editingVariable.id]: editVarValue }));
      } else {
        setRevealedKeys((prev) => {
          const copy = { ...prev };
          delete copy[editingVariable.id];
          return copy;
        });
      }
      await loadVariables();
      await loadHistory();
      setEditingVariable(null);
    } catch (err: unknown) {
      setEditVarError(getErrorMessage(err, "Failed to update variable"));
    } finally {
      setEditVarLoading(false);
    }
  };

  const toggleReveal = async (item: VariableItem) => {
    if (!activeEnv) return;
    if (revealedKeys[item.id]) {
      const copy = { ...revealedKeys };
      delete copy[item.id];
      setRevealedKeys(copy);
      return;
    }
    try {
      const res = await api.post(`/environments/${activeEnv.id}/variables/${item.id}/reveal`);
      setRevealedKeys((prev) => ({ ...prev, [item.id]: res.data.value }));
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Could not decrypt secret"));
    }
  };

  const handleParseDiff = async () => {
    if (!activeEnv || !rawEnvText.trim()) return;
    try {
      const res = await api.post(`/environments/${activeEnv.id}/variables/parse-diff`, {
        raw_env: rawEnvText
      });
      setDiffItems(res.data);
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Error parsing env file"));
    }
  };

  const handleCommitBulk = async () => {
    if (!activeEnv || !diffItems) return;
    try {
      await api.post(`/environments/${activeEnv.id}/variables/commit-bulk`, {
        raw_env: rawEnvText,
        sensitive_keys: diffItems.filter((item) => item.is_sensitive).map((item) => item.key)
      });
      setShowBulkModal(false);
      setRawEnvText("");
      setDiffItems(null);
      loadVariables();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to apply changes"));
    }
  };

  const handleRevertLog = async (log: HistoryItem) => {
    if (!activeEnv) return;
    if (!confirm(`Are you sure you want to revert changes for "${log.key}"?`)) return;

    setRevertingLogId(log.id);
    try {
      await api.post(`/environments/${activeEnv.id}/history/${log.id}/revert`);
      await loadVariables();
      await loadHistory();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to revert change"));
    } finally {
      setRevertingLogId(null);
    }
  };

  // Export .env with safe handling for masked secrets and clipboard failures
  const handleExportEnv = async () => {
    if (variables.length === 0) {
      alert("No variables available to export.");
      return;
    }

    const unrevealedSensitive = variables.filter(
      (v) => v.is_sensitive && revealedKeys[v.id] === undefined
    );

    if (unrevealedSensitive.length > 0) {
      const proceed = confirm(
        `Notice: ${unrevealedSensitive.length} sensitive variable(s) are still masked and will be exported as placeholders. ` +
        "To include actual secret values, reveal them first. Continue with export?"
      );

      if (!proceed) return;
    }

    const content = variables
      .map((v) => {
        const value =
          revealedKeys[v.id] !== undefined
            ? revealedKeys[v.id]
            : v.value;

        return `${v.key}=${value}`;
      })
      .join("\n");

    const envFileName = activeEnv
      ? `.env.${activeEnv.name.toLowerCase()}`
      : ".env";

    let downloadUrl: string | null = null;

    try {
      const blob = new Blob([content], {
        type: "text/plain;charset=utf-8",
      });

      downloadUrl = URL.createObjectURL(blob);

      const downloadLink = document.createElement("a");
      downloadLink.href = downloadUrl;
      downloadLink.download = envFileName;

      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);

      window.setTimeout(() => {
        if (downloadUrl) {
          URL.revokeObjectURL(downloadUrl);
        }
      }, 1000);

      let clipboardCopied = false;

      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(content);
          clipboardCopied = true;
        } catch {
          clipboardCopied = false;
        }
      }

      if (clipboardCopied) {
        alert(`Downloaded ${envFileName} and copied its contents to the clipboard.`);
      } else {
        alert(`Downloaded ${envFileName}. Automatic clipboard copying was unavailable or failed.`);
      }
    } catch (err: unknown) {
      if (downloadUrl) {
        URL.revokeObjectURL(downloadUrl);
      }

      alert(getErrorMessage(err, "Could not export the environment file."));
    }
  };
  // Unauthenticated View
  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-slate-950 text-slate-100">
        <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-8 shadow-2xl">
          <div className="flex items-center justify-center gap-3 mb-6">
            <KeyRound className="w-8 h-8 text-emerald-400" />
            <h1 className="text-2xl font-bold tracking-tight">EnvShare</h1>
          </div>

          {pendingInviteToken && (
            <div className="mb-6 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-xs text-emerald-300 flex items-start gap-2.5">
              <UserPlus className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-emerald-200">Project Invitation Received</p>
                <p className="text-slate-300 mt-0.5">
                  You have been invited to collaborate on a project. Create an account below or sign in to accept your invitation.
                </p>
              </div>
            </div>
          )}

          {/* Tab bar (visible when not in reset mode) */}
          {authMode !== "reset" && (
            <div className="flex border-b border-slate-800 mb-6">
              <button
                onClick={() => { setAuthMode("login"); setAuthError(""); setAuthSuccessMsg(""); }}
                className={`flex-1 py-2 font-medium text-sm border-b-2 transition ${authMode === "login" ? "border-emerald-500 text-emerald-400" : "border-transparent text-slate-400 hover:text-slate-200"}`}
              >
                Sign In
              </button>
              <button
                onClick={() => { setAuthMode("register"); setAuthError(""); setAuthSuccessMsg(""); }}
                className={`flex-1 py-2 font-medium text-sm border-b-2 transition ${authMode === "register" ? "border-emerald-500 text-emerald-400" : "border-transparent text-slate-400 hover:text-slate-200"}`}
              >
                Register
              </button>
            </div>
          )}

          {authError && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 p-3 rounded-lg text-sm mb-4">
              {authError}
            </div>
          )}

          {authSuccessMsg && (
            <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 p-3 rounded-lg text-sm mb-4">
              {authSuccessMsg}
            </div>
          )}

          {/* 1. Reset Password Form (Arrived via email link) */}
          {authMode === "reset" && (
            <form onSubmit={handleResetPassword} className="space-y-4">
              <h2 className="text-base font-semibold text-slate-200 mb-1">Set New Password</h2>
              <p className="text-xs text-slate-400 mb-3">Please choose a secure password of at least 8 characters.</p>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">New Password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                  placeholder="................................."
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Confirm New Password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                  placeholder=".................................."
                />
              </div>

              <button
                type="submit"
                disabled={authLoading}
                className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-2 rounded-lg text-sm transition mt-2 shadow-lg shadow-emerald-950"
              >
                {authLoading ? "Updating Password..." : "Update Password"}
              </button>

              <div className="text-center pt-2">
                <button
                  type="button"
                  onClick={() => { setAuthMode("login"); setAuthError(""); setAuthSuccessMsg(""); }}
                  className="text-xs text-slate-400 hover:text-slate-200 transition"
                >
                  Back to Sign In
                </button>
              </div>
            </form>
          )}

          {/* 2. Forgot Password Request Form */}
          {authMode === "forgot" && (
            <form onSubmit={handleForgotPassword} className="space-y-4">
              <h2 className="text-base font-semibold text-slate-200 mb-1">Recover Password</h2>
              <p className="text-xs text-slate-400 mb-3">
                Enter your account email and we'll send you a secure reset link valid for 15 minutes.
              </p>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                  placeholder="developer@example.com"
                />
              </div>

              <button
                type="submit"
                disabled={authLoading}
                className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-2 rounded-lg text-sm transition mt-2 shadow-lg shadow-emerald-950"
              >
                {authLoading ? "Sending Link..." : "Send Reset Link"}
              </button>

              <div className="text-center pt-2">
                <button
                  type="button"
                  onClick={() => { setAuthMode("login"); setAuthError(""); setAuthSuccessMsg(""); }}
                  className="text-xs text-slate-400 hover:text-slate-200 transition"
                >
                  ← Back to Sign In
                </button>
              </div>
            </form>
          )}

          {/* 3. Standard Login / Register Form */}
          {(authMode === "login" || authMode === "register") && (
            <form onSubmit={handleAuthSubmit} className="space-y-4">
              {authMode === "register" && (
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Full Name</label>
                  <input
                    type="text"
                    required
                    value={authName}
                    onChange={(e) => setAuthName(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                    placeholder="Engineering Lead"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                  placeholder="developer@example.com"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-medium text-slate-400">Password</label>
                  {authMode === "login" && (
                    <button
                      type="button"
                      onClick={() => { setAuthMode("forgot"); setAuthError(""); setAuthSuccessMsg(""); }}
                      className="text-xs text-emerald-400 hover:text-emerald-300 transition"
                    >
                      Forgot password?
                    </button>
                  )}
                </div>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                  placeholder="................................"
                />
              </div>

              <button
                type="submit"
                disabled={authLoading}
                className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-2 rounded-lg text-sm transition mt-2 shadow-lg shadow-emerald-950"
              >
                {authLoading ? "Please wait..." : authMode === "login" ? "Sign In" : "Create Account"}
              </button>
            </form>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <header className="border-b border-slate-800 bg-slate-900/60 px-6 py-3 flex items-center justify-between backdrop-blur">
        <div className="flex items-center gap-3">
          <KeyRound className="w-6 h-6 text-emerald-400" />
          <span className="font-bold text-lg tracking-tight">EnvShare</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-sm font-medium">{currentUser?.name}</p>
            <p className="text-xs text-slate-400">{currentUser?.email}</p>
          </div>
          <button
            onClick={handleLogout}
            className="p-2 text-slate-400 hover:text-red-400 rounded-lg hover:bg-slate-800 transition"
            title="Sign Out"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Invitation Feedback Banner (INV-02, FE-02) */}
      {inviteFeedback && (
        <div
          className={`px-6 py-2.5 text-xs flex items-center justify-between border-b ${inviteFeedback.type === "success"
            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
            : "bg-red-500/10 border-red-500/30 text-red-400"
            }`}
        >
          <div className="flex items-center gap-2">
            {inviteFeedback.type === "success" ? (
              <CheckCircle className="w-4 h-4 text-emerald-400" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-red-400" />
            )}
            <span>{inviteFeedback.message}</span>
          </div>
          <button
            onClick={() => setInviteFeedback(null)}
            className="text-slate-400 hover:text-slate-200"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-64 border-r border-slate-800 bg-slate-900/30 p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Projects</span>
              <button
                onClick={() => setShowNewProjectModal(true)}
                className="p-1 hover:bg-slate-800 text-emerald-400 rounded"
                title="Create Project"
              >
                <FolderPlus className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-1">
              {projects.map((proj) => (
                <button
                  key={proj.id}
                  onClick={() => {
                    setActiveProject(proj);
                    setActiveEnv(proj.environments[0] || null);
                  }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition font-medium flex items-center justify-between ${activeProject?.id === proj.id
                    ? "bg-emerald-600/10 text-emerald-400 border border-emerald-500/20"
                    : "text-slate-300 hover:bg-slate-800/60"
                    }`}
                >
                  <span className="truncate">{proj.name}</span>
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                    {proj.role}
                  </span>
                </button>
              ))}
              {projects.length === 0 && (
                <p className="text-xs text-slate-500 py-2">No projects found. Create one above.</p>
              )}
            </div>
          </div>
        </aside>

        <main className="flex-1 flex flex-col p-8 overflow-y-auto">
          {activeProject ? (
            <>
              <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-800">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-2xl font-bold tracking-tight">{activeProject.name}</h2>
                    <span
                      className={`text-[10px] uppercase font-mono px-2 py-0.5 rounded font-semibold ${activeProject.role === "OWNER"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                        : "bg-sky-500/10 text-sky-400 border border-sky-500/30"
                        }`}
                    >
                      {activeProject.role === "OWNER" ? "Project Owner" : "Collaborator (Member)"}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{activeProject.description || "No description provided."}</p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => {
                      setShowMembersModal(true);
                      loadMembers();
                    }}
                    className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg text-sm transition"
                    title="View Project Team"
                  >
                    <Users className="w-4 h-4 text-sky-400" />
                    Members
                  </button>

                  {activeProject?.role === "OWNER" && (
                    <button
                      onClick={() => {
                        setInviteUrl("");
                        setCopiedInvite(false);
                        setShowInviteModal(true);
                      }}
                      className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg text-sm transition"
                    >
                      <UserPlus className="w-4 h-4 text-emerald-400" />
                      Invite Collaborator
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setShowSnapshotsModal(true);
                      loadSnapshots();
                    }}
                    className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg text-sm transition"
                  >
                    <Camera className="w-4 h-4 text-amber-400" />
                    Snapshots
                  </button>
                  <button
                    onClick={() => setViewHistory(!viewHistory)}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition ${viewHistory ? "bg-emerald-600 text-white" : "bg-slate-800 hover:bg-slate-700 text-slate-200"
                      }`}
                  >
                    <History className="w-4 h-4" />
                    {viewHistory ? "Show Variables" : "History Log"}
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-2 mb-6">
                {activeProject.environments.map((env) => (
                  <button
                    key={env.id}
                    onClick={() => setActiveEnv(env)}
                    className={`px-4 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition ${activeEnv?.id === env.id
                      ? "bg-emerald-500 text-slate-950 shadow-md font-bold"
                      : "bg-slate-900 border border-slate-800 text-slate-300 hover:bg-slate-800"
                      }`}
                  >
                    {env.name.toUpperCase()}
                  </button>
                ))}
              </div>

              {!viewHistory ? (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-sm font-medium text-slate-400">
                      {variables.length} Variable{variables.length !== 1 ? "s" : ""} Defined
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleExportEnv}
                        className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg text-sm transition"
                        title="Download .env file and copy to clipboard"
                      >
                        <Download className="w-4 h-4 text-emerald-400" />
                        Export .env
                      </button>
                      <button
                        onClick={() => setShowBulkModal(true)}
                        className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg text-sm transition"
                      >
                        <ClipboardPaste className="w-4 h-4 text-sky-400" />
                        Smart Import (.env)
                      </button>
                      <button
                        onClick={() => setShowAddVarModal(true)}
                        className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1.5 rounded-lg text-sm transition"
                      >
                        <Plus className="w-4 h-4" />
                        Add Variable
                      </button>
                    </div>
                  </div>

                  <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/40">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                        <tr>
                          <th className="px-6 py-3">Key</th>
                          <th className="px-6 py-3">Value</th>
                          <th className="px-6 py-3">Type</th>
                          <th className="px-6 py-3 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {variables.map((item) => (
                          <tr key={item.id} className="hover:bg-slate-900/40 transition">
                            <td className="px-6 py-3 font-mono font-medium text-slate-200">
                              {item.key}
                            </td>
                            <td className="px-6 py-3 font-mono text-slate-300">
                              {item.is_sensitive ? (
                                <span>{revealedKeys[item.id] || "••••••••"}</span>
                              ) : (
                                item.value
                              )}
                            </td>
                            <td className="px-6 py-3">
                              {item.is_sensitive ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                  <Shield className="w-3 h-3" />
                                  Sensitive
                                </span>
                              ) : (
                                <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                                  Standard
                                </span>
                              )}
                            </td>
                            <td className="px-6 py-3 text-right space-x-2">
                              {item.is_sensitive && (
                                <button
                                  onClick={() => toggleReveal(item)}
                                  className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition"
                                  title={revealedKeys[item.id] ? "Mask secret" : "Reveal secret"}
                                >
                                  {revealedKeys[item.id] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                </button>
                              )}
                              <button
                                onClick={() => openEditVariableModal(item)}
                                className="p-1.5 text-slate-400 hover:text-emerald-400 hover:bg-slate-800 rounded transition"
                                title="Edit Variable"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => deleteVariable(item.id)}
                                className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-800 rounded transition"
                                title="Delete Variable"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </td>
                          </tr>
                        ))}
                        {variables.length === 0 && (
                          <tr>
                            <td colSpan={4} className="px-6 py-8 text-center text-slate-500">
                              No environment variables present. Click "Add Variable" or "Smart Import" to start.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-2">Audit Timeline</h3>
                  <div className="space-y-3">
                    {historyLogs.map((log) => (
                      <div
                        key={log.id}
                        className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex items-start justify-between gap-4"
                      >
                        <div className="flex items-start gap-4">
                          <div className="mt-1">
                            {log.action === "CREATE" && <CheckCircle className="w-5 h-5 text-emerald-400" />}
                            {log.action === "UPDATE" && <AlertTriangle className="w-5 h-5 text-amber-400" />}
                            {log.action === "DELETE" && <Trash2 className="w-5 h-5 text-red-400" />}
                          </div>
                          <div>
                            <p className="text-sm text-slate-200">
                              <span className="font-semibold text-emerald-400">{log.user_name}</span>{" "}
                              {log.action.toLowerCase()}d variable{" "}
                              <span className="font-mono bg-slate-800 px-1 py-0.5 rounded text-xs text-slate-300">
                                {log.key}
                              </span>
                            </p>
                            {log.action === "UPDATE" && (
                              <div className="flex items-center gap-2 mt-2 font-mono text-xs text-slate-400">
                                <span className="line-through text-red-400/80">{log.old_value}</span>
                                <ArrowRight className="w-3 h-3" />
                                <span className="text-emerald-400">{log.new_value}</span>
                              </div>
                            )}
                            <p className="text-[11px] text-slate-500 mt-1">
                              {new Date(log.created_at).toLocaleString()}
                            </p>
                          </div>
                        </div>

                        {/* Owner Revert Button */}
                        {activeProject.role === "OWNER" && log.old_value && !["[ENCRYPTED]", "[REDACTED]"].includes(log.old_value) && (
                          <button
                            onClick={() => handleRevertLog(log)}
                            disabled={revertingLogId === log.id}
                            className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded border border-slate-700 transition disabled:opacity-50 shrink-0"
                            title="Restore previous value"
                          >
                            <RotateCcw
                              className={`w-3.5 h-3.5 ${revertingLogId === log.id ? "animate-spin" : "text-amber-400"
                                }`}
                            />
                            Revert
                          </button>
                        )}
                      </div>
                    ))}
                    {historyLogs.length === 0 && (
                      <p className="text-sm text-slate-500">No activity recorded for this environment yet.</p>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-500">
              Select or create a project to get started.
            </div>
          )}
        </main>
      </div>

      {showNewProjectModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h3 className="text-lg font-bold mb-4">Create New Project</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Project Name</label>
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  placeholder="e.g. Mobile Application"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Description (Optional)</label>
                <input
                  type="text"
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  placeholder="Internal settings and secrets"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowNewProjectModal(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                onClick={createProject}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {showAddVarModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h3 className="text-lg font-bold mb-4">Add Variable</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Key Name</label>
                <input
                  type="text"
                  value={newVarKey}
                  onChange={(e) => setNewVarKey(e.target.value)}
                  placeholder="e.g. DATABASE_URL"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Value</label>
                <input
                  type="text"
                  value={newVarVal}
                  onChange={(e) => setNewVarVal(e.target.value)}
                  placeholder="e.g. postgresql://user:pass@localhost:5432/db"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="sens-checkbox"
                  checked={newVarSensitive}
                  onChange={(e) => setNewVarSensitive(e.target.checked)}
                  className="rounded border-slate-800 text-emerald-500 focus:ring-0"
                />
                <label htmlFor="sens-checkbox" className="text-xs text-slate-300 flex items-center gap-1.5 cursor-pointer">
                  <Shield className="w-3.5 h-3.5 text-amber-400" />
                  Encrypt as Sensitive Variable (AES-256-GCM)
                </label>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowAddVarModal(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                onClick={addVariable}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
              >
                Save Variable
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Variable Modal */}
      {editingVariable && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold flex items-center gap-2">
                <Pencil className="w-5 h-5 text-emerald-400" />
                Edit Variable
              </h3>
              <button
                onClick={() => setEditingVariable(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveEditVariable} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Key</label>
                <input
                  type="text"
                  disabled
                  value={editingVariable.key}
                  className="w-full bg-slate-950/60 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-400 font-mono cursor-not-allowed"
                />
                <p className="text-[11px] text-slate-500 mt-1">Variable key cannot be changed after creation.</p>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Value {editVarFetching && <span className="text-emerald-400 text-[10px] ml-1">(decrypting...)</span>}
                </label>
                <textarea
                  required
                  rows={3}
                  value={editVarValue}
                  onChange={(e) => setEditVarValue(e.target.value)}
                  placeholder="Enter variable value"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="editVarSensitive"
                  checked={editVarSensitive}
                  disabled={editingVariable.is_sensitive}
                  onChange={(e) => setEditVarSensitive(e.target.checked)}
                  className="rounded border-slate-800 text-emerald-500 focus:ring-0"
                />
                <label htmlFor="editVarSensitive" className="text-xs text-slate-300 cursor-pointer">
                  Sensitive (Encrypted at rest with AES-256-GCM)
                </label>
              </div>
              {editingVariable.is_sensitive && (
                <p className="text-[10px] text-amber-400/80 -mt-2">
                  Known secret variables cannot be downgraded to plaintext.
                </p>
              )}

              {editVarError && (
                <div className="bg-red-500/10 border border-red-500/30 text-red-400 p-2.5 rounded-lg text-xs">
                  {editVarError}
                </div>
              )}

              <div className="flex justify-end gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => setEditingVariable(null)}
                  className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editVarLoading}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50"
                >
                  {editVarLoading ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Team Members Modal (UI-06) */}
      {showMembersModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold flex items-center gap-2">
                <Users className="w-5 h-5 text-sky-400" />
                Project Members
              </h3>
              <button
                onClick={() => setShowMembersModal(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 max-h-60 overflow-y-auto">
              {loadingMembers ? (
                <p className="text-xs text-slate-400 text-center py-4">Loading members...</p>
              ) : projectMembers.length > 0 ? (
                projectMembers.map((member) => (
                  <div
                    key={member.id}
                    className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex items-center justify-between text-xs"
                  >
                    <div>
                      <p className="font-medium text-slate-200">{member.name}</p>
                      <p className="text-slate-400">{member.email}</p>
                    </div>
                    <span
                      className={`uppercase text-[10px] font-mono px-2 py-0.5 rounded font-bold ${member.role === "OWNER"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                        : "bg-slate-800 text-slate-300"
                        }`}
                    >
                      {member.role}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-slate-500 text-center py-4">No member details available.</p>
              )}
            </div>

            <div className="flex justify-end mt-6">
              <button
                onClick={() => setShowMembersModal(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Invite Modal with Role Clarification (UI-05) */}
      {showInviteModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h3 className="text-lg font-bold mb-2">Invite Collaborator</h3>
            <p className="text-xs text-slate-400 mb-4">
              Generate a unique, single-use invite link valid for 48 hours. Collaborators receive standard team permissions to view, add, and update variables.
            </p>

            <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 mb-5 text-xs text-slate-300 flex items-center justify-between">
              <span>Assigned Role:</span>
              <span className="font-mono font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                MEMBER (Collaborator)
              </span>
            </div>

            {!inviteUrl ? (
              <div className="py-2 text-center">
                <button
                  onClick={generateInviteLink}
                  disabled={inviteLoading}
                  className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition inline-flex items-center gap-2 shadow-lg shadow-emerald-950"
                >
                  <UserPlus className="w-4 h-4" />
                  {inviteLoading ? "Generating..." : "Generate Invite Link"}
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Shareable Link</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={inviteUrl}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-300 focus:outline-none"
                    />
                    <button
                      onClick={handleCopyInviteLink}
                      className="bg-slate-800 hover:bg-slate-700 text-emerald-400 p-2 rounded-lg transition shrink-0"
                      title="Copy to clipboard"
                    >
                      {copiedInvite ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                {copiedInvite && (
                  <p className="text-xs text-emerald-400 flex items-center gap-1">
                    <CheckCircle className="w-3.5 h-3.5" /> Copied to clipboard!
                  </p>
                )}
              </div>
            )}

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowInviteModal(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {showBulkModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-2xl shadow-2xl flex flex-col max-h-[85vh]">
            <h3 className="text-lg font-bold mb-2">Smart Import (.env Text)</h3>
            <p className="text-xs text-slate-400 mb-4">
              Paste your raw environment text. Comments (#) and blank lines are ignored automatically.
            </p>

            {!diffItems ? (
              <div className="flex-1 flex flex-col">
                <textarea
                  value={rawEnvText}
                  onChange={(e) => setRawEnvText(e.target.value)}
                  placeholder={`# Database configuration\nPORT=8000\nDATABASE_URL="postgres://user:pass@host/db"\n# Mode flag\nDEBUG=false`}
                  className="w-full h-64 bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono focus:outline-none focus:border-emerald-500 resize-none"
                />
                <div className="flex justify-end gap-3 mt-4">
                  <button
                    onClick={() => { setShowBulkModal(false); setRawEnvText(""); }}
                    className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleParseDiff}
                    className="bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
                  >
                    Parse & Review Diff
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="text-xs text-slate-400 mb-2">
                  Review the actions below before applying changes to <strong>{activeEnv?.name}</strong>:
                </div>
                <div className="flex-1 overflow-y-auto border border-slate-800 rounded-lg bg-slate-950 p-2 space-y-2">
                  {diffItems.map((item, idx) => (
                    <div
                      key={item.key}
                      className={`p-3 rounded-lg border flex items-center justify-between text-xs font-mono ${item.status === "NEW"
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                        : item.status === "UPDATE"
                          ? "bg-amber-500/10 border-amber-500/30 text-amber-300"
                          : "bg-slate-900 border-slate-800 text-slate-400"
                        }`}
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`px-1.5 py-0.5 rounded font-bold text-[10px] uppercase ${item.status === "NEW"
                              ? "bg-emerald-500 text-slate-950"
                              : item.status === "UPDATE"
                                ? "bg-amber-500 text-slate-950"
                                : "bg-slate-800 text-slate-400"
                              }`}
                          >
                            {item.status}
                          </span>
                          <span className="font-bold">{item.key}</span>
                        </div>
                        {item.status === "UPDATE" ? (
                          <div className="flex items-center gap-2">
                            <span className="line-through text-slate-500">{item.is_sensitive ? "[REDACTED]" : item.old_value}</span>
                            <ArrowRight className="w-3 h-3 text-slate-400" />
                            <span>{item.is_sensitive ? "[REDACTED]" : item.new_value}</span>
                          </div>
                        ) : (
                          <div>{item.is_sensitive ? "[REDACTED]" : item.new_value}</div>
                        )}
                      </div>

                      {item.status !== "UNCHANGED" && (
                        <label className="flex items-center gap-1.5 cursor-pointer ml-4">
                          <input
                            type="checkbox"
                            checked={item.is_sensitive}
                            disabled={item.is_existing_sensitive}
                            onChange={(e) => {
                              const updated = [...diffItems];
                              updated[idx].is_sensitive = e.target.checked;
                              setDiffItems(updated);
                            }}
                            className="rounded border-slate-800 text-emerald-500 focus:ring-0"
                          />
                          <span className="text-[11px] text-slate-300">Sensitive</span>
                        </label>
                      )}
                    </div>
                  ))}
                  {diffItems.length === 0 && (
                    <p className="text-xs text-slate-500 p-4 text-center">No valid key-value pairs recognized.</p>
                  )}
                </div>

                <div className="flex justify-between items-center mt-4">
                  <button
                    onClick={() => setDiffItems(null)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    ← Back to editor
                  </button>
                  <div className="flex gap-3">
                    <button
                      onClick={() => { setShowBulkModal(false); setDiffItems(null); }}
                      className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleCommitBulk}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
                    >
                      Apply Import
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Snapshots & Disaster Recovery Modal */}
      {showSnapshotsModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-2xl shadow-2xl flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-bold flex items-center gap-2">
                <Camera className="w-5 h-5 text-amber-400" />
                Environment Snapshots & Disaster Recovery
              </h3>
            </div>
            <p className="text-xs text-slate-400 mb-4">
              Roll back entire environments to previous versions. A safety backup of the current state is automatically created before any restore.
            </p>

            {/* Create Manual Snapshot */}
            <div className="flex gap-2 mb-4 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
              <input
                type="text"
                value={newSnapshotName}
                onChange={(e) => setNewSnapshotName(e.target.value)}
                placeholder="Snapshot name (e.g., Pre-v2 Release)"
                className="flex-1 bg-transparent border-none text-xs text-slate-200 focus:outline-none px-2"
              />
              <button
                onClick={handleCreateSnapshot}
                className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-3 py-1.5 rounded font-medium transition"
              >
                Take Snapshot
              </button>
            </div>

            {/* Snapshots List */}
            <div className="flex-1 overflow-y-auto space-y-2 border border-slate-800 rounded-lg bg-slate-950 p-3">
              {snapshots.map((snap) => (
                <div
                  key={snap.id}
                  className="p-3 bg-slate-900 border border-slate-800 rounded-lg flex items-center justify-between"
                >
                  <div>
                    <p className="text-sm font-semibold text-slate-200">{snap.name}</p>
                    <div className="flex items-center gap-3 text-[11px] text-slate-400 mt-1">
                      <span>{snap.var_count} variables</span>
                      <span>•</span>
                      <span>Created by {snap.created_by_name}</span>
                      <span>•</span>
                      <span>{new Date(snap.created_at).toLocaleString()}</span>
                    </div>
                  </div>

                  {activeProject?.role === "OWNER" && (
                    <button
                      onClick={() => handleRollbackSnapshot(snap)}
                      disabled={isRollingBack === snap.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded font-medium transition disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isRollingBack === snap.id ? "animate-spin" : ""}`} />
                      Restore Snapshot
                    </button>
                  )}
                </div>
              ))}

              {snapshots.length === 0 && (
                <p className="text-xs text-slate-500 text-center py-6">
                  No snapshots captured yet. Take a snapshot before major updates.
                </p>
              )}
            </div>

            <div className="flex justify-end mt-4">
              <button
                onClick={() => setShowSnapshotsModal(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
