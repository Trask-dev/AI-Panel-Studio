/**
 * SummaryModal — 主持人结语弹窗
 *
 * 从 discussionStore 读取 summary / isSummarizing / summaryError。
 * Loading 态模拟"主持人正在撰写总结"(2-3s 动效)。
 */

import React from "react";
import { useDiscussionStore } from "../stores/discussionStore";

export function SummaryModal({ onClose }) {
  const summary = useDiscussionStore((s) => s.summary);
  const isSummarizing = useDiscussionStore((s) => s.isSummarizing);
  const summaryError = useDiscussionStore((s) => s.summaryError);
  const generateSummary = useDiscussionStore((s) => s.generateSummary);
  const meta = useDiscussionStore((s) => s.meta);

  const handleGenerate = () => {
    if (meta.id) generateSummary(meta.id);
  };

  return (
    <div className="summary-modal-overlay" data-testid="summary-modal">
      <div className="summary-modal">
        {/* Header */}
        <div className="summary-modal__header">
          <h2 className="summary-modal__title">📋 主持人结语</h2>
          {onClose && (
            <button className="summary-modal__close" onClick={onClose} aria-label="关闭">
              ✕
            </button>
          )}
        </div>

        {/* Body */}
        <div className="summary-modal__body">
          {/* Loading 态 */}
          {isSummarizing && (
            <div className="summary-loading" data-testid="summary-loading">
              <div className="summary-loading__spinner" />
              <p className="summary-loading__text">
                主持人正在撰写总结，请稍候...
              </p>
              <p className="summary-loading__hint">
                正在基于 {meta.roundCount} 轮讨论内容进行综合提炼
              </p>
            </div>
          )}

          {/* Error 态 */}
          {summaryError && !isSummarizing && (
            <div className="summary-error" data-testid="summary-error">
              <p>⚠️ {summaryError}</p>
              <button className="btn btn--primary" onClick={handleGenerate}>
                重试
              </button>
            </div>
          )}

          {/* 无总结时 → 生成按钮 */}
          {!summary && !isSummarizing && !summaryError && (
            <div className="summary-empty" data-testid="summary-empty">
              <p>讨论已结束，是否生成主持人结语？</p>
              <button
                className="btn btn--primary"
                onClick={handleGenerate}
                data-testid="generate-summary-btn"
              >
                📝 生成总结
              </button>
            </div>
          )}

          {/* 总结内容 */}
          {summary && !isSummarizing && (
            <div className="summary-content" data-testid="summary-content">
              <div className="summary-section">
                <div
                  className="summary-text"
                  dangerouslySetInnerHTML={{
                    __html: markdownToHtml(summary.content),
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 简易 Markdown → HTML (仅处理标题和段落)
// ---------------------------------------------------------------------------
function markdownToHtml(md) {
  return md
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<[hl/])/gm, "<p>")
    .replace(/([^>])$/gm, "$1</p>");
}
