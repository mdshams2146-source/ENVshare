import React, { useState, useEffect } from "react";
import { api } from "./api";
import type { User, Project, Environment, VariableItem, DiffItem, HistoryItem } from "./types";
import {
  KeyRound, Shield, Eye, EyeOff, Plus, Trash2, ClipboardPaste,
  History, LogOut, CheckCircle, AlertTriangle, ArrowRight, UserPlus, FolderPlus, Download
} from "lucide-react";

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authName, setAuthName] = useState("");
  const [authError, setAuthError] = useState("");

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

  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");

  const [showBulkModal, setShowBulkModal] = useState(false);
  const [rawEnvText, setRawEnvText] = useState("");
  const [diffItems, setDiffItems] = useState<DiffItem[] | null>(null);

  const [viewHistory, setViewHistory] = useState(false);
  const [historyLogs, setHistoryLogs] = useState<HistoryItem[]>([]);

  useEffect(() => {
    if (token) {
      api.get("/auth/me")
        .then((res) => {
          setCurrentUser(res.data);
          loadProjects();
        })
        .catch(() => handleLogout());
    }
  }, [token]);

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    try {
      const endpoint = authMode === "login" ? "/auth/login" : "/auth/register";
      const payload = authMode === "login"
        ? { email: authEmail, password: authPassword }
        : { name: authName, email: authEmail, password: authPassword };

      const res = await api.post(endpoint, payload);
      localStorage.setItem("token", res.data.access_token);
      setToken(res.data.access_token);
      setCurrentUser(res.data.user);
      loadProjects();
    } catch (err: any) {
      const msg =
        err.response?.data?.detail ||
        (typeof err.response?.data === "string" ? err.response?.data : null) ||
        err.message ||
        "Authentication failed";
      setAuthError(typeof msg === "object" ? JSON.stringify(msg) : msg);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setCurrentUser(null);
    setProjects([]);
    setActiveProject(null);
    setActiveEnv(null);
  };

  const loadProjects = async () => {
    try {
      const res = await api.get("/projects");
      setProjects(res.data);
      if (res.data.length > 0 && !activeProject) {
        setActiveProject(res.data[0]);
        if (res.data[0].environments.length > 0) {
          setActiveEnv(res.data[0].environments[0]);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const createProject = async () => {
    if (!newProjectName.trim()) return;
    try {
      const res = await api.post("/projects", {
        name: newProjectName,
        description: newProjectDesc
      });
      setShowNewProjectModal(false);
      setNewProjectName("");
      setNewProjectDesc("");
      loadProjects();
      setActiveProject(res.data);
      setActiveEnv(res.data.environments[0]);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Error creating project");
    }
  };

  const inviteMember = async () => {
    if (!activeProject || !inviteEmail.trim()) return;
    try {
      await api.post(`/projects/${activeProject.id}/members`, { email: inviteEmail });
      alert(`User ${inviteEmail} invited successfully! (Email alert sent via Resend)`);
      setShowInviteModal(false);
      setInviteEmail("");
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to invite member");
    }
  };

  useEffect(() => {
    if (activeEnv) {
      loadVariables();
      if (viewHistory) loadHistory();
    }
  }, [activeEnv, viewHistory]);

  const loadVariables = async () => {
    if (!activeEnv) return;
    try {
      const res = await api.get(`/environments/${activeEnv.id}/variables`);
      setVariables(res.data);
      setRevealedKeys({});
    } catch (err) {
      console.error(err);
    }
  };

  const loadHistory = async () => {
    if (!activeEnv) return;
    try {
      const res = await api.get(`/environments/${activeEnv.id}/history`);
      setHistoryLogs(res.data);
    } catch (err) {
      console.error(err);
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
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to add variable");
    }
  };

  const deleteVariable = async (varId: string) => {
    if (!activeEnv || !confirm("Are you sure you want to delete this variable?")) return;
    try {
      await api.delete(`/environments/${activeEnv.id}/variables/${varId}`);
      loadVariables();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Delete failed");
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
    } catch (err: any) {
      alert(err.response?.data?.detail || "Could not decrypt secret");
    }
  };

  const handleParseDiff = async () => {
    if (!activeEnv || !rawEnvText.trim()) return;
    try {
      const res = await api.post(`/environments/${activeEnv.id}/variables/parse-diff`, {
        raw_env: rawEnvText
      });
      setDiffItems(res.data);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Error parsing env file");
    }
  };

  const handleCommitBulk = async () => {
    if (!activeEnv || !diffItems) return;
    try {
      await api.post(`/environments/${activeEnv.id}/variables/commit-bulk`, {
        items: diffItems
      });
      setShowBulkModal(false);
      setRawEnvText("");
      setDiffItems(null);
      loadVariables();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to apply changes");
    }
  };

  const handleExportEnv = () => {
    if (variables.length === 0) {
      alert("No variables available to export.");
      return;
    }
    const content = variables
      .map((v) => `${v.key}=${revealedKeys[v.id] !== undefined ? revealedKeys[v.id] : v.value}`)
      .join("\n");
    navigator.clipboard.writeText(content);
    alert("Environment variables copied to clipboard!");
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-slate-950 text-slate-100">
        <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-8 shadow-2xl">
          <div className="flex items-center justify-center gap-3 mb-6">
            <KeyRound className="w-8 h-8 text-emerald-400" />
            <h1 className="text-2xl font-bold tracking-tight">EnvShare</h1>
          </div>

          <div className="flex border-b border-slate-800 mb-6">
            <button
              onClick={() => { setAuthMode("login"); setAuthError(""); }}
              className={`flex-1 py-2 font-medium text-sm border-b-2 transition ${authMode === "login" ? "border-emerald-500 text-emerald-400" : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setAuthMode("register"); setAuthError(""); }}
              className={`flex-1 py-2 font-medium text-sm border-b-2 transition ${authMode === "register" ? "border-emerald-500 text-emerald-400" : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
            >
              Register
            </button>
          </div>

          {authError && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 p-3 rounded-lg text-sm mb-4">
              {authError}
            </div>
          )}

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
                  placeholder="Mohammad Shamsuddin"
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
              <label className="block text-xs font-medium text-slate-400 mb-1">Password</label>
              <input
                type="password"
                required
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                placeholder="••••••••••••"
              />
            </div>
            <button
              type="submit"
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2 rounded-lg text-sm transition mt-2 shadow-lg shadow-emerald-950"
            >
              {authMode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>
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
                  <h2 className="text-2xl font-bold tracking-tight">{activeProject.name}</h2>
                  <p className="text-xs text-slate-400 mt-1">{activeProject.description || "No description provided."}</p>
                </div>
                <div className="flex items-center gap-3">
                  {activeProject.role === "OWNER" && (
                    <button
                      onClick={() => setShowInviteModal(true)}
                      className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg text-sm transition"
                    >
                      <UserPlus className="w-4 h-4 text-emerald-400" />
                      Invite Member
                    </button>
                  )}
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
                        title="Copy .env format to clipboard"
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
                      <div key={log.id} className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex items-start gap-4">
                        <div className="mt-1">
                          {log.action === "CREATE" && <CheckCircle className="w-5 h-5 text-emerald-400" />}
                          {log.action === "UPDATE" && <AlertTriangle className="w-5 h-5 text-amber-400" />}
                          {log.action === "DELETE" && <Trash2 className="w-5 h-5 text-red-400" />}
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-slate-200">
                            <span className="font-semibold text-emerald-400">{log.user_name}</span>{" "}
                            {log.action.toLowerCase()}d variable{" "}
                            <span className="font-mono bg-slate-800 px-1 py-0.5 rounded text-xs text-slate-300">{log.key}</span>
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
                  Encrypt as Sensitive Variable (AES-256)
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

      {showInviteModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h3 className="text-lg font-bold mb-4">Invite Team Member</h3>
            <p className="text-xs text-slate-400 mb-4">
              Enter the registered email of the user to grant them access to this project.
            </p>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">User Email</label>
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@example.com"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowInviteModal(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                onClick={inviteMember}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
              >
                Send Invite
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
              Paste your raw environment text. Comments (#) and blank lines will be ignored automatically.
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
                          <span className={`px-1.5 py-0.5 rounded font-bold text-[10px] uppercase ${item.status === "NEW"
                              ? "bg-emerald-500 text-slate-950"
                              : item.status === "UPDATE"
                                ? "bg-amber-500 text-slate-950"
                                : "bg-slate-800 text-slate-400"
                            }`}>
                            {item.status}
                          </span>
                          <span className="font-bold">{item.key}</span>
                        </div>
                        {item.status === "UPDATE" ? (
                          <div className="flex items-center gap-2">
                            <span className="line-through text-slate-500">{item.old_value}</span>
                            <ArrowRight className="w-3 h-3 text-slate-400" />
                            <span>{item.new_value}</span>
                          </div>
                        ) : (
                          <div>{item.new_value}</div>
                        )}
                      </div>

                      {item.status !== "UNCHANGED" && (
                        <label className="flex items-center gap-1.5 cursor-pointer ml-4">
                          <input
                            type="checkbox"
                            checked={item.is_sensitive}
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
    </div>
  );
}