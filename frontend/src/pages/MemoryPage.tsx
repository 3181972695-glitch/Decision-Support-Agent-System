import { useState, useEffect, type FormEvent } from "react";
import {
  listMemoriesApi,
  createMemoryApi,
  deleteMemoryApi,
  updateMemoryApi,
  clearAllMemoriesApi,
} from "../services/api";
import type { MemoryItem } from "../services/api";

const TYPE_COLORS: Record<string, { bg: string; fg: string }> = {
  decision: { bg: "#eef2ff", fg: "#4338ca" },
  preference: { bg: "#f0fdf4", fg: "#15803d" },
  context: { bg: "#fefce8", fg: "#a16207" },
};

const TYPE_LABELS: Record<string, string> = {
  decision: "Decision",
  preference: "Preference",
  context: "Context",
};

function getTypeColor(type: string) {
  return TYPE_COLORS[type] ?? { bg: "#f3f4f6", fg: "#374151" };
}

function formatDate(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function MemoryPage() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("");

  // New memory form
  const [newContent, setNewContent] = useState("");
  const [newType, setNewType] = useState("decision");
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState("");
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadMemories = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listMemoriesApi(filterType || undefined);
      setMemories(data.memories);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memories");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMemories();
  }, [filterType]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    setSaving(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const result = await createMemoryApi(newContent.trim(), newType);
      console.log("[MEMORY] saved id=", result.id);
      setNewContent("");
      await loadMemories();
      setSuccessMsg("Memory saved successfully.");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      console.error("[MEMORY] save error:", err);
      setError(err instanceof Error ? err.message : "Failed to create memory");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteMemoryApi(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete memory");
    }
  };

  const startEdit = (mem: MemoryItem) => {
    setEditingId(mem.id);
    setEditContent(mem.content);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditContent("");
  };

  const handleUpdate = async (id: number) => {
    if (!editContent.trim()) return;
    try {
      const updated = await updateMemoryApi(id, editContent.trim());
      setMemories((prev) => prev.map((m) => (m.id === id ? updated : m)));
      setEditingId(null);
      setEditContent("");
      setSuccessMsg("Memory updated.");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update memory");
    }
  };

  const handleClearAll = async () => {
    if (!confirm("Delete all memories?")) return;
    try {
      await clearAllMemoriesApi();
      setMemories([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear memories");
    }
  };

  return (
    <main>
      <h1>User Memory</h1>
      <p>Persistent memory for previous decisions, preferences, and context. This information is injected into expert debates for continuity.</p>

      {/* ── New Memory Form ── */}
      <form onSubmit={handleCreate}>
        <label htmlFor="mem-type">Memory Type</label>
        <select
          id="mem-type"
          value={newType}
          onChange={(e) => setNewType(e.target.value)}
          disabled={saving}
          className="expert-select"
        >
          <option value="decision">Decision</option>
          <option value="preference">Preference</option>
          <option value="context">Context</option>
        </select>

        <label htmlFor="mem-content">Content</label>
        <textarea
          id="mem-content"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          placeholder="e.g. User prefers low-risk strategies"
          rows={2}
          disabled={saving}
          className="question-panel__input"
          required
        />

        <button type="submit" disabled={saving || !newContent.trim()}>
          {saving ? "Saving..." : "Save Memory"}
        </button>
      </form>

      {/* ── Success message ── */}
      {successMsg && <p className="success">{successMsg}</p>}

      {error && <p className="error">{error}</p>}

      {/* ── Filter + Clear ── */}
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", margin: "1rem 0" }}>
        <label htmlFor="mem-filter" style={{ fontSize: "0.85rem", whiteSpace: "nowrap" }}>Filter:</label>
        <select
          id="mem-filter"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="expert-select"
          style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem" }}
        >
          <option value="">All types</option>
          <option value="decision">Decision</option>
          <option value="preference">Preference</option>
          <option value="context">Context</option>
        </select>

        <button
          onClick={handleClearAll}
          className="btn btn--secondary"
          style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem", marginLeft: "auto" }}
        >
          Clear All
        </button>
      </div>

      {/* ── Memory List ── */}
      {loading && (
        <div className="status-banner status-banner--live">
          <span className="spinner" />
          <span>Loading memories...</span>
        </div>
      )}

      {!loading && memories.length === 0 && (
        <div className="waiting-card">
          <p>No memories yet. Save your first memory above.</p>
        </div>
      )}

      <div className="memory-list">
        {memories.map((mem) => {
          const c = getTypeColor(mem.memory_type);
          return (
            <div
              key={mem.id}
              className="message memory-card"
              style={{ background: c.bg, borderLeftColor: c.fg }}
            >
              <div className="message__header">
                <span className="message__badge" style={{ background: c.fg, color: "#fff" }}>
                  {TYPE_LABELS[mem.memory_type] ?? mem.memory_type}
                </span>
                <span className="message__label">{formatDate(mem.created_at)}</span>
                <button
                  className="memory-card__edit"
                  onClick={() => startEdit(mem)}
                  title="Edit"
                  style={{ background: "none", border: "none", color: "#6366f1", cursor: "pointer", fontSize: "0.8rem", padding: "0.15rem 0.3rem" }}
                >
                  ✏️
                </button>
                <button
                  className="memory-card__delete"
                  onClick={() => handleDelete(mem.id)}
                  title="Delete"
                >
                  ✕
                </button>
              </div>
              {editingId === mem.id ? (
                <div>
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="question-panel__input"
                    rows={2}
                    style={{ width: "100%", marginBottom: "0.5rem" }}
                  />
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button onClick={() => handleUpdate(mem.id)} className="btn btn--primary" style={{ padding: "0.35rem 0.8rem", fontSize: "0.8rem" }}>Save</button>
                    <button onClick={cancelEdit} className="btn btn--secondary" style={{ padding: "0.35rem 0.8rem", fontSize: "0.8rem" }}>Cancel</button>
                  </div>
                </div>
              ) : (
                <p>{mem.content}</p>
              )}
              {mem.relevance != null && (
                <span className="memory-card__relevance">
                  Relevance: {Math.round(mem.relevance * 100)}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </main>
  );
}

export default MemoryPage;
