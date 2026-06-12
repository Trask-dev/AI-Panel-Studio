/**
 * TranscriptPanel — 消息列表组件
 *
 * Props:
 *   messages:     TranscriptEntry[]
 *   guests:       Guest[] (用于 guest_name/color lookup)
 *   streamingId:  string|null (当前流式中的 entry id)
 */

import React, { useEffect, useRef } from "react";

export function TranscriptPanel({ messages = [], guests = [], streamingId = null }) {
  const bottomRef = useRef(null);

  // 新消息到达时自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, messages[messages.length - 1]?.content]);

  if (messages.length === 0) {
    return (
      <div className="transcript-panel" data-testid="transcript-panel">
        <div className="transcript-empty" data-testid="transcript-empty">
          等待讨论开始...
        </div>
      </div>
    );
  }

  let lastRound = 0;

  return (
    <div className="transcript-panel" data-testid="transcript-panel">
      {messages.map((msg) => {
        const showDivider = msg.round_number !== lastRound && lastRound > 0;
        lastRound = msg.round_number;
        const isStreaming = msg.id === streamingId;

        return (
          <React.Fragment key={msg.id}>
            {showDivider && msg.round_number > 0 && (
              <div className="transcript-round-divider" data-testid="round-divider">
                <span>── 第 {msg.round_number} 轮 ──</span>
              </div>
            )}
            <TranscriptEntry
              message={msg}
              isStreaming={isStreaming}
              color={msg.guest_color || getGuestColor(guests, msg.guest_id)}
            />
          </React.Fragment>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}

const ENTRY_TYPE_CN = {
  opening_statement: "🎤 开场白", position_statement: "🗣️ 立场陈述",
  speech: "💬 发言", interjection: "⚡ 插话", rebuttal: "↩️ 反驳",
  supplement: "➕ 补充", question: "❓ 提问", answer: "✅ 回答",
  closing_statement: "🏁 总结", host_summary: "📋 主持总结",
};

function TranscriptEntry({ message, isStreaming, color }) {
  return (
    <div
      className={`transcript-entry${isStreaming ? " transcript-entry--streaming" : ""}`}
      data-testid={`transcript-entry-${message.id}`}
    >
      <div
        className="transcript-entry__bar"
        style={{ backgroundColor: color }}
        data-testid="entry-bar"
      />
      <div className="transcript-entry__body">
        <div className="transcript-entry__header">
          <span className="entry-speaker" style={{ color }}>
            {message.guest_name}
          </span>
          {message.guest_title && (
            <span className="entry-role">{message.guest_title}</span>
          )}
          <span className="entry-type-label">
            {ENTRY_TYPE_CN[message.entry_type] || message.entry_type}
          </span>
          {isStreaming && (
            <span className="streaming-badge" data-testid="streaming-badge">
              正在发言
            </span>
          )}
        </div>
        <p className="entry-content" data-testid="entry-content">
          {message.content}
          {isStreaming && <span className="streaming-cursor">█</span>}
        </p>
      </div>
    </div>
  );
}

function getGuestColor(guests, guestId) {
  const g = guests.find((g) => g.id === guestId);
  return g?.color || "#9090a0";
}
