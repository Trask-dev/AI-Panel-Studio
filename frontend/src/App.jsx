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

      es.onerror = () => {
        // EventSource 自动重连，无需处理
      };
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
  const [actionLoading, setActionLoading] = useState(false); // 防重复点击

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
      // 不自动进入演播厅 —— SDD #6: 等用户确认阵容
    } catch (e) {
      setError("创建失败: " + (e.message || "未知错误"));
    }
  };

  const handleSelectDiscussion = async (d) => {
    try {
      // 关闭旧 SSE + 清空全部状态
      if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
      store.reset();
      setDiscId(d.id);
      setLineupConfirmed(false);
      setShowSummary(false);
      setError(null);

      const detail = await api.getDiscussion(d.id);
      // 防御: 确保 guests 严格来自当前 discussion
      const safeGuests = (detail.guests || []).filter(g => g.discussion_id === d.id);
      store.initDiscussion(detail.discussion, safeGuests);

      if (d.status === "setup" && safeGuests.length === 0) {
        const gen = await api.generateGuests(d.id);
        const genGuests = (gen.guests || []).filter(g => g.discussion_id === d.id);
        store.initDiscussion(detail.discussion, genGuests);
      }

      if (d.status !== "setup") {
        setLineupConfirmed(true);
        const msgs = await api.fetchMessages(d.id);
        store.loadHistory((msgs && msgs.items) ? msgs.items : []);
      }
    } catch (e) {
      setError("加载讨论失败: " + (e.message || ""));
    }
  };

  const handleAdvanceRound = async () => {
    if (!discId) return;
    try {
      const r = await api.advanceRound(discId);
      store.onRoundAdvance({ round_number: r.round_count });
      const msgs = await api.fetchMessages(discId);
      store.loadHistory((msgs && msgs.items) ? msgs.items : []);
      if (r.status === "summarizing") {
        store.onDiscussionStatusChange({ status: "summarizing" });
      }
    } catch (e) {
      setError("推进轮次失败: " + (e.message || ""));
    }
  };

  const handleEnd = async () => {
    if (!discId) return;
    try {
      await api.endDiscussion(discId);
      store.onDiscussionStatusChange({ status: "summarizing" });
      setShowSummary(true);
    } catch (e) {
      setError("结束失败: " + (e.message || ""));
    }
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
        </div>
        <div className="app-header__right">
          {discId && store.meta.status === "setup" && !host && (
            <button className="btn btn--primary" disabled={actionLoading} onClick={async () => {
              setActionLoading(true);
              try {
                const gen = await api.generateGuests(discId);
                const detail = await api.getDiscussion(discId);
                store.initDiscussion(detail.discussion, gen.guests || []);
              } catch (e) { setError("生成失败: " + (e.message || "")); }
              finally { setActionLoading(false); }
            }}>
              {actionLoading ? "生成中..." : "🤖 生成嘉宾"}
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
                } catch (e) { setError("重新生成失败: " + (e.message || "")); }
              }}>
                🔄 重新生成
              </button>
            </>
          )}
          {discId && store.meta.status === "setup" && host && lineupConfirmed && (
            <button className="btn btn--primary" onClick={async () => {
              try {
                await api.startDiscussion(discId);
                store.onDiscussionStatusChange({ discussion_id: discId, status: "active" });
                const msgs = await api.fetchMessages(discId);
                store.loadHistory((msgs && msgs.items) ? msgs.items : []);
              } catch (e) { setError("开始失败: " + (e.message || "")); }
            }}>
              🎬 开始讨论
            </button>
          )}
          {discId && store.meta.status === "active" && (
            <>
              <button className="btn btn--secondary" onClick={handleAdvanceRound}>
                ▶ 下一轮
              </button>
              <button className="btn btn--secondary" onClick={handleEnd}>
                ■ 结束
              </button>
            </>
          )}
        </div>
      </header>

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

            {/* SDD #6: 阵容确认环节 */}
            {store.meta.status === "setup" && host && !lineupConfirmed && (
              <div style={{ zIndex: 10, marginBottom: 16, display: "flex", gap: 12, alignItems: "center" }}>
                <span style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>
                  请确认嘉宾阵容：
                </span>
                <button
                  className="btn btn--primary"
                  style={{ fontSize: "1rem", padding: "10px 24px" }}
                  onClick={() => setLineupConfirmed(true)}
                >
                  ✅ 确认阵容
                </button>
                <button
                  className="btn btn--secondary"
                  style={{ fontSize: "1rem", padding: "10px 24px" }}
                  onClick={async () => {
                    try {
                      const gen = await api.generateGuests(discId);
                      const detail = await api.getDiscussion(discId);
                      store.initDiscussion(detail.discussion, gen.guests || []);
                    } catch (e) {
                      setError("重新生成失败: " + (e.message || ""));
                    }
                  }}
                >
                  🔄 重新生成
                </button>
              </div>
            )}

            {/* 阵容已确认：显示开始按钮 */}
            {store.meta.status === "setup" && host && lineupConfirmed && (
              <div style={{ zIndex: 10, marginBottom: 16 }}>
                <button
                  className="btn btn--primary"
                  style={{ fontSize: "1.1rem", padding: "12px 32px" }}
                  onClick={async () => {
                    try {
                      await api.startDiscussion(discId);
                      store.onDiscussionStatusChange({ discussion_id: discId, status: "active" });
                      const msgs = await api.fetchMessages(discId);
                      store.loadHistory((msgs && msgs.items) ? msgs.items : []);
                    } catch (e) {
                      setError("开始失败: " + (e.message || ""));
                    }
                  }}
                >
                  🎬 开始讨论
                </button>
              </div>
            )}

            {/* 无嘉宾：生成按钮 */}
            {store.meta.status === "setup" && !host && (
              <div style={{ zIndex: 10, marginBottom: 16 }}>
                <button
                  className="btn btn--primary"
                  style={{ fontSize: "1.1rem", padding: "12px 32px" }}
                  onClick={async () => {
                    try {
                      const gen = await api.generateGuests(discId);
                      const detail = await api.getDiscussion(discId);
                      store.initDiscussion(detail.discussion, gen.guests || []);
                    } catch (e) {
                      setError("生成失败: " + (e.message || ""));
                    }
                  }}
                >
                  🤖 生成嘉宾阵容
                </button>
              </div>
            )}

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
              <AnalysisPanel discussionId={discId} />
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
    </div>
  );
}

// =========================================================================
// AnalysisPanel
// =========================================================================
function AnalysisPanel({ discussionId }) {
  const [consensus, setConsensus] = useState([]);
  const [divergences, setDivergences] = useState([]);

  useEffect(() => {
    if (discussionId) {
      api.fetchConsensus(discussionId).then((d) => setConsensus((d && d.items) || []));
      api.fetchDivergences(discussionId).then((d) => setDivergences((d && d.items) || []));
    }
  }, [discussionId]);

  return (
    <>
      <div className="panel-tabs">
        <span className="panel-tab panel-tab--active">✅ 共识 ({consensus.length})</span>
        <span className="panel-tab">⚡ 分歧 ({divergences.length})</span>
      </div>
      <div className="panel-content">
        {consensus.map((c) => (
          <div className="consensus-card" key={c.id}>
            <div className="consensus-card__header">
              <span className="consensus-icon">✅</span>
              <span className="consensus-confidence">{Math.round((c.confidence || 0) * 100)}%</span>
            </div>
            <p className="consensus-card__content">{c.content}</p>
            <div className="consensus-bar">
              <div className="consensus-bar__fill" style={{ "--fill": c.confidence || 0 }} />
            </div>
          </div>
        ))}
        {divergences.map((d) => (
          <div className="divergence-card" key={d.id}>
            <div className="divergence-card__header">
              <span className="divergence-icon">⚡</span>
              <span className={`severity-badge severity-badge--${d.severity || "moderate"}`}>{d.severity}</span>
            </div>
            <p className="divergence-card__content">{d.content}</p>
          </div>
        ))}
        {consensus.length === 0 && divergences.length === 0 && (
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", padding: "1rem" }}>
            讨论开始后将实时显示共识与分歧
          </p>
        )}
      </div>
    </>
  );
}
