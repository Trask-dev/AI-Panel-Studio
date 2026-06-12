/**
 * SummaryModal — 主持人结语弹窗
 *
 * 通过 isOpen 控制显隐，默认关闭。点击遮罩层或 ✕ 按钮关闭。
 * 从 discussionStore 读取 summary / isSummarizing / summaryError。
 */

import React from "react";
import { useDiscussionStore } from "../stores/discussionStore";

export function SummaryModal({ isOpen = false, onClose }) {
  const summary = useDiscussionStore((s) => s.summary);
  const isSummarizing = useDiscussionStore((s) => s.isSummarizing);
  const summaryError = useDiscussionStore((s) => s.summaryError);
  const generateSummary = useDiscussionStore((s) => s.generateSummary);
  const meta = useDiscussionStore((s) => s.meta);

  const handleGenerate = () => {
    if (meta.id) generateSummary(meta.id);
  };

  const handleClose = () => {
    if (onClose) onClose();
  };

  const handleOverlayClick = (e) => {
    // 点击遮罩层（非弹窗内容区域）关闭
    if (e.target === e.currentTarget) {
      handleClose();
    }
  };

  // Bug 修复 1: isOpen 控制显隐，默认 false 不显示
  if (!isOpen) return null;

  return (
    <div
      className="summary-modal-overlay"
      data-testid="summary-modal"
      onClick={handleOverlayClick}
      style={{ display: "flex" }}
    >
      <div className="summary-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header — Bug 修复 2: 关闭按钮始终渲染 */}
        <div className="summary-modal__header">
          <h2 className="summary-modal__title">📋 主持人结语</h2>
          <button
            className="summary-modal__close"
            onClick={handleClose}
            aria-label="关闭"
            type="button"
            style={{ position: "relative", zIndex: 101 }}
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="summary-modal__body">
          {isSummarizing && (
            <div className="summary-loading" data-testid="summary-loading">
              <div className="summary-loading__spinner" />
              <p className="summary-loading__text">主持人正在撰写总结，请稍候...</p>
              <p className="summary-loading__hint">
                正在基于 {meta.roundCount} 轮讨论内容进行综合提炼
              </p>
            </div>
          )}

          {summaryError && !isSummarizing && (
            <div className="summary-error" data-testid="summary-error">
              <p>⚠️ {summaryError}</p>
              <button className="btn btn--primary" onClick={handleGenerate}>
                重试
              </button>
            </div>
          )}

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
// 简易 Markdown → HTML
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
