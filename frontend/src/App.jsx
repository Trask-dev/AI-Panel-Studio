import React, { useState, useEffect, useRef } from "react";
import { useDiscussionStore } from "./stores/discussionStore";
import * as api from "./services/api";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { SummaryModal } from "./components/SummaryModal";

export default function App() {
  const store = useDiscussionStore();
  const [discId, setDiscId] = useState(null);
  const sseRef = useRef(null);

  // SSE 实时事件流（替换轮询）
  useEffect(() => {
    if (discId && store.meta.status === "active") {
      const es = api.connectSSE(discId);
      sseRef.current = es;

      es.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data);
          const type = ev.type;
          const p = ev.payload;
          if (type === "transcript_append" && p) store.onTranscriptAppend(p);
          else if (type === "guest_status_change" && p) store.onGuestStatusChange(p);
          else if (type === "snapshot_update" && p) store.onSnapshotUpdate(p);
          else if (type === "discussion_status_change" && p) store.onDiscussionStatusChange(p);
          else if (type === "round_advance" && p) store.onRoundAdvance(p);
          else if (type === "consensus_update" && p) store.onConsensusUpdate(p);
          else if (type === "divergence_update" && p) store.onDivergenceUpdate(p);
        } catch {}
      };

      es.onopen = () => setSseConnected(true);
      es.onerror = () => setSseConnected(false);
    }
    return () => {
      if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
    };
  }, [discId, store.meta.status]);
  const [showSummary, setShowSummary] = useState(false);
  const [discussions, setDiscussions] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newTopic, setNewTopic] = useState("AI会取代人类工作吗");
  const [newExpertCount, setNewExpertCount] = useState(4);  // SDD #3: 用户指定专家人数
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lineupConfirmed, setLineupConfirmed] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [sseConnected, setSseConnected] = useState(false);
  const asyncStatus = useDiscussionStore((s) => s.asyncStatus);

  useEffect(() => {
    api
      .listDiscussions()
      .then((d) => {
        setDiscussions(Array.isArray(d) ? d : []);
        setLoading(false);
      })
      .catch((e) => {
        setError("无法连接后端，请确认服务已启动在 8000 端口");
        setLoading(false);
      });
  }, []);

  const handleCreate = async () => {
    if (!newTopic.trim()) return;
    try {
      const result = await api.createDiscussion({ topic: newTopic.trim(), expertCount: newExpertCount });
      const list = await api.listDiscussions();
      setDiscussions(Array.isArray(list) ? list : []);
      setShowCreate(false);
      setNewTopic("");
      setLineupConfirmed(false);
      // 关闭旧连接 + 清空状态
      if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
      store.reset();
      setDiscId(null);
      setSseConnected(false);
    } catch (e) {
      setError("创建失败: " + (e.message || "未知错误"));
    }
  };

  const runAsync = async (type, message, fn) => {
    store.setAsyncStatus(type, message);
    try {
      await fn();
      store.clearAsyncStatus();
    } catch (e) {
      // 失败时保留状态栏显示错误，3 秒后自动清除
      store.setAsyncStatus("error", message + "失败: " + (e.message || "请重试"));
      setTimeout(() => store.clearAsyncStatus(), 5000);
    }
  };

  const handleSelectDiscussion = async (d) => {
    if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
    store.reset();
    setDiscId(d.id);
    setLineupConfirmed(false);
    setShowSummary(false);
    setError(null);

    const detail = await api.getDiscussion(d.id);
    const safeGuests = (detail.guests || []).filter(g => g.discussion_id === d.id);
    store.initDiscussion(detail.discussion, safeGuests);

    if (d.status === "setup" && safeGuests.length === 0) {
      await runAsync("generating", "AI 正在生成嘉宾阵容…", async () => {
        const gen = await api.generateGuests(d.id);
        store.initDiscussion(detail.discussion, gen.guests || []);
      });
    }

    if (d.status !== "setup") {
      setLineupConfirmed(true);
      const msgs = await api.fetchMessages(d.id);
      store.loadHistory((msgs && msgs.items) ? msgs.items : []);
      api.fetchConsensus(d.id).then(r => { if (r?.items) store.onConsensusUpdate({ items: r.items }); });
      api.fetchDivergences(d.id).then(r => { if (r?.items) store.onDivergenceUpdate({ items: r.items }); });
    }
  };

  const handleAdvanceRound = async () => {
    if (!discId) return;
    await runAsync("advancing", "AI 正在生成发言并分析共识…", async () => {
      const r = await api.advanceRound(discId);
      store.onRoundAdvance({ round_number: r.round_count });
      const msgs = await api.fetchMessages(discId);
      store.loadHistory((msgs && msgs.items) ? msgs.items : []);
      if (r.consensus) store.onConsensusUpdate({ items: r.consensus });
      if (r.divergences) store.onDivergenceUpdate({ items: r.divergences });
      if (r.status === "summarizing") store.onDiscussionStatusChange({ status: "summarizing" });
    });
  };

  const handleEnd = async () => {
    if (!discId) return;
    await runAsync("summarizing", "AI 正在生成总结…", async () => {
      await api.endDiscussion(discId);
      store.onDiscussionStatusChange({ status: "summarizing" });
      const msgs = await api.fetchMessages(discId);
      store.loadHistory((msgs && msgs.items) ? msgs.items : []);
      setShowSummary(true);
    });
  };

  const guests = store.guests || [];
  const host = guests.find((g) => g.role === "host");
  const experts = guests.filter((g) => g.role === "expert");

  const statusColors = {
    active: "var(--success)",
    finished: "var(--info)",
    summarizing: "var(--warning)",
    setup: "var(--text-muted)",
  };

  const statusLabels = {
    active: "进行中",
    finished: "已结束",
    summarizing: "总结中",
    setup: "配置中",
  };

  // ---- Render ----
  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__left">
          <span className="app-logo">
            <span className="app-logo__icon">🎬</span>
            <span className="app-logo__text">AI Panel Studio</span>
          </span>
        </div>
        <div className="app-header__center">
          <h1 className="discussion-topic">
            {store.meta.topic || "选择一个讨论"}
          </h1>
          {store.meta.status && (
            <span className={`status-badge status-badge--${store.meta.status}`}>
              ● {store.meta.status}
            </span>
          )}
          {store.meta.roundCount > 0 && (
            <span className="round-indicator">
              Round <strong>{store.meta.roundCount}</strong>
            </span>
          )}
          {discId && store.meta.status === "active" && (
            <span style={{ fontSize: "0.65rem", color: sseConnected ? "var(--success)" : "var(--danger)" }}>
              {sseConnected ? "🟢 实时" : "🔴 断连"}
            </span>
          )}
        </div>
        <div className="app-header__right">
          {discId && store.meta.status === "setup" && !host && (
            <button className="btn btn--primary" disabled={asyncStatus.type !== "idle"} onClick={async () => {
              await runAsync("generating", "AI 正在生成嘉宾阵容…", async () => {
                const gen = await api.generateGuests(discId);
                const detail = await api.getDiscussion(discId);
                store.initDiscussion(detail.discussion, gen.guests || []);
              });
            }}>
              {asyncStatus.type === "generating" ? "⏳ 生成中…" : "🤖 生成嘉宾"}
            </button>
          )}
          {discId && store.meta.status === "setup" && host && !lineupConfirmed && (
            <>
              <button className="btn btn--primary" onClick={() => setLineupConfirmed(true)}>
                ✅ 确认阵容
              </button>
              <button className="btn btn--secondary" onClick={async () => {
                try {
                  const gen = await api.generateGuests(discId);
                  const detail = await api.getDiscussion(discId);
                  store.initDiscussion(detail.discussion, gen.guests || []);
                  api.fetchConsensus(discId).then(r => { if (r && r.items) store.onConsensusUpdate({ items: r.items }); });
                  api.fetchDivergences(discId).then(r => { if (r && r.items) store.onDivergenceUpdate({ items: r.items }); });
                } catch (e) { setError("重新生成失败: " + (e.message || "")); }
              }}>
                🔄 重新生成
              </button>
            </>
          )}
          {discId && store.meta.status === "setup" && host && lineupConfirmed && (
            <button className="btn btn--primary" disabled={asyncStatus.type !== "idle"} onClick={async () => {
              await runAsync("starting", "AI 正在生成开场白…", async () => {
                await api.startDiscussion(discId);
                store.onDiscussionStatusChange({ discussion_id: discId, status: "active" });
                const msgs = await api.fetchMessages(discId);
                store.loadHistory((msgs && msgs.items) ? msgs.items : []);
                api.fetchConsensus(discId).then(r => { if (r?.items) store.onConsensusUpdate({ items: r.items }); });
                api.fetchDivergences(discId).then(r => { if (r?.items) store.onDivergenceUpdate({ items: r.items }); });
              });
            }}>
              {asyncStatus.type === "starting" ? "⏳ 准备中…" : "🎬 开始讨论"}
            </button>
          )}
          {discId && store.meta.status === "active" && (
            <>
              <button className="btn btn--secondary" onClick={handleAdvanceRound}
                disabled={asyncStatus.type !== "idle"}>
                {asyncStatus.type === "advancing" ? "⏳ 生成中…" : "▶ 下一轮"}
              </button>
              <button className="btn btn--secondary" onClick={handleEnd}
                disabled={asyncStatus.type !== "idle"}>
                {asyncStatus.type === "summarizing" ? "⏳ 总结中…" : "■ 结束"}
              </button>
            </>
          )}
        </div>
      </header>

      {/* 全局异步操作状态栏 */}
      {asyncStatus.type !== "idle" && (
        <div style={{
          height: 32, display: "flex", alignItems: "center", justifyContent: "center",
          background: asyncStatus.type === "error" ? "rgba(217,74,74,0.08)" : "var(--bg-secondary)",
          borderBottom: "1px solid var(--border-default)",
          color: asyncStatus.type === "error" ? "var(--danger)" : "var(--gold)",
          fontSize: "var(--text-sm)", gap: 8, flexShrink: 0,
        }}>
          <span className="streaming-cursor" style={{ display: "inline-block" }} />
          {asyncStatus.message}
          {asyncStatus.startedAt && (
            <span style={{ color: "var(--text-muted)", fontSize: "var(--text-xs)", fontFamily: "var(--font-mono)" }}>
              {Math.floor((Date.now() - asyncStatus.startedAt) / 1000)}s
            </span>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <main style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16, padding: 40 }}>
          <p style={{ fontSize: "2rem" }}>⚠️</p>
          <p style={{ color: "var(--text-secondary)", fontSize: "1rem" }}>{error}</p>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
            <code style={{ color: "var(--gold)" }}>cd backend && uvicorn app.main:app --port 8000</code>
          </p>
          <button className="btn btn--primary" onClick={() => { setError(null); setLoading(true); window.location.reload(); }}>
            重试
          </button>
        </main>
      )}

      {/* Loading */}
      {loading && !error && (
        <main style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <p style={{ color: "var(--text-secondary)" }}>加载中...</p>
        </main>
      )}

      {/* Studio View */}
      {!loading && !error && discId && (
        <main className="studio-view">
          <section className="studio-stage">
            <div className="stage-lighting" aria-hidden="true" />

            {host && (
              <div className="stage-host-area">
                <GuestCard guest={host} />
              </div>
            )}
            <div className="stage-experts-row">
              {experts.map((g) => (
                <GuestCard key={g.id} guest={g} />
              ))}
            </div>
          </section>
          <div className="studio-bottom">
            <section className="live-transcript">
              <div className="transcript-header">
                <h2 className="transcript-header__title">📝 现场转录</h2>
                <span className="auto-scroll-badge auto-scroll-badge--on">▼ 自动滚动</span>
              </div>
              <div className="transcript-entries">
                <TranscriptPanel
                  messages={store.messages}
                  guests={guests}
                  streamingId={store.streamingId}
                />
              </div>
            </section>
            <aside className="analysis-panel">
              <AnalysisPanel />
            </aside>
          </div>
        </main>
      )}

      {/* Discussion List */}
      {!loading && !error && !discId && (
        <main className="discussion-grid">
          {discussions.map((d) => (
            <article
              key={d.id}
              className="discussion-card"
              style={{ "--card-accent": statusColors[d.status] || "var(--text-muted)" }}
              onClick={() => handleSelectDiscussion(d)}
            >
              <div className="discussion-card__accent" />
              <div className="discussion-card__body">
                <div className="discussion-card__header">
                  <span className={`discussion-status discussion-status--${d.status}`}>
                    ● {statusLabels[d.status] || d.status}
                  </span>
                  {d.round_count > 0 && (
                    <span className="discussion-round">Round {d.round_count}</span>
                  )}
                </div>
                <h3 className="discussion-card__title">{d.topic}</h3>
                <div className="discussion-card__footer">
                  <span className="discussion-time">🕐 {new Date(d.created_at).toLocaleString()}</span>
                </div>
              </div>
            </article>
          ))}
          {showCreate ? (
            <article className="discussion-card" style={{ "--card-accent": "var(--gold)" }}>
              <div className="discussion-card__accent" />
              <div className="discussion-card__body">
                <h3 className="discussion-card__title">新建讨论</h3>
                <input
                  value={newTopic}
                  onChange={(e) => setNewTopic(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  placeholder="输入讨论话题..."
                  autoFocus
                  style={{
                    width: "100%", padding: "8px 12px", borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border-default)", background: "var(--bg-tertiary)",
                    color: "var(--text-primary)", fontSize: "var(--text-sm)", marginTop: 8,
                  }}
                />
                <div style={{ marginTop: 8 }}>
                  <label style={{ color: "var(--text-secondary)", fontSize: "var(--text-xs)", marginRight: 8 }}>
                    专家人数：
                  </label>
                  <select
                    value={newExpertCount}
                    onChange={(e) => setNewExpertCount(Number(e.target.value))}
                    style={{
                      padding: "6px 10px", borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--border-default)", background: "var(--bg-tertiary)",
                      color: "var(--text-primary)", fontSize: "var(--text-sm)",
                    }}
                  >
                    {[2, 3, 4, 5, 6, 7, 8].map((n) => (
                      <option key={n} value={n}>{n} 人</option>
                    ))}
                  </select>
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <button className="btn btn--primary" onClick={handleCreate}>创建</button>
                  <button className="btn btn--secondary" onClick={() => setShowCreate(false)}>取消</button>
                </div>
              </div>
            </article>
          ) : (
            <article
              className="discussion-card"
              style={{ "--card-accent": "var(--gold)", cursor: "pointer" }}
              onClick={() => setShowCreate(true)}
            >
              <div className="discussion-card__accent" />
              <div className="discussion-card__body">
                <h3 className="discussion-card__title">+ 新建讨论</h3>
                <p className="discussion-card__desc">输入话题，AI 自动生成主持人和专家阵容</p>
              </div>
            </article>
          )}
        </main>
      )}

      <SummaryModal isOpen={showSummary} onClose={() => setShowSummary(false)} />
    </div>
  );
}

// =========================================================================
// GuestCard
// =========================================================================
function GuestCard({ guest }) {
  const status = guest.status || "idle";
  const statusClass =
    status === "speaking" ? "guest-card--speaking"
    : status === "thinking" ? "guest-card--thinking"
    : status === "waiting" ? "guest-card--waiting" : "";
  const isHost = guest.role === "host";

  return (
    <div
      className={`guest-card ${isHost ? "guest-card--host" : "guest-card--expert"} ${statusClass}`}
      style={{ "--guest-color": guest.color || "#9090a0" }}
    >
      <div className="guest-card__avatar">
        <div className="guest-avatar" style={{ "--guest-color": guest.color || "#9090a0" }}>
          {guest.name?.[0] || "?"}
        </div>
        {isHost ? (
          <span className="guest-role-badge guest-role-badge--host">🎤 主持</span>
        ) : (
          <span className="guest-stance-label" style={{ "--guest-color": guest.color }}>
            {guest.stance_label || "嘉宾"}
          </span>
        )}
      </div>
      <div className="guest-card__info">
        <h3 className="guest-name">{guest.name || "未知"}</h3>
        <p className="guest-title">{guest.title || ""}</p>
      </div>
      <div className="guest-card__status">
        <span className={`guest-status guest-status--${status}`}>
          {status === "speaking" ? "● 发言中"
            : status === "thinking" ? "◉ 思考中"
            : status === "waiting" ? "◐ 冷却中"
            : "● 待机"}
        </span>
      </div>
      {/* 思考气泡: thinking 状态且存在 public_thought 时显示 */}
      {status === "thinking" && guest.snapshot?.public_thought && (
        <div className="thinking-bubble" style={{ "--guest-color": guest.color || "#9090a0", display: "block" }}>
          <p className="thinking-bubble__text">{guest.snapshot.public_thought}</p>
        </div>
      )}
    </div>
  );
}

// =========================================================================
// AnalysisPanel
// =========================================================================
function AnalysisPanel() {
  const consensus = useDiscussionStore((s) => s.consensus);
  const divergences = useDiscussionStore((s) => s.divergences);

  return (
    <div className="panel-content" style={{ display: "flex", flexDirection: "column", padding: "var(--space-md)", overflowY: "auto", flex: 1, gap: "var(--space-md)" }}>
      {/* 共识区 */}
      <div style={{ marginBottom: "var(--space-lg)" }}>
        <h3 style={{ color: "var(--text-primary)", fontSize: "var(--text-sm)", fontWeight: 600, marginBottom: "var(--space-sm)" }}>
          ✅ 共识 ({consensus.length})
        </h3>
        {consensus.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>推进讨论后出现</p>
        ) : (
          consensus.map((c, i) => (
            <div className="consensus-card" key={c.id || `c-${i}`} style={{ marginBottom: "var(--space-sm)" }}>
              <div className="consensus-card__header">
                <span className="consensus-confidence">{Math.round((c.confidence || 0) * 100)}%</span>
              </div>
              <p className="consensus-card__content">{c.content}</p>
              <div className="consensus-bar">
                <div className="consensus-bar__fill" style={{ "--fill": c.confidence || 0 }} />
              </div>
            </div>
          ))
        )}
      </div>

      {/* 分歧区 */}
      <div>
        <h3 style={{ color: "var(--text-primary)", fontSize: "var(--text-sm)", fontWeight: 600, marginBottom: "var(--space-sm)" }}>
          ⚡ 分歧 ({divergences.length})
        </h3>
        {divergences.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>推进讨论后出现</p>
        ) : (
          divergences.map((d, i) => (
            <div className="divergence-card" key={d.id || `d-${i}`} style={{ marginBottom: "var(--space-sm)" }}>
              <div className="divergence-card__header">
                <span className={`severity-badge severity-badge--${d.severity || "moderate"}`}>{d.severity}</span>
              </div>
              <p className="divergence-card__content">{d.content}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
