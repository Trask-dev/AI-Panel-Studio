/**
 * SummaryModal 组件 + Store Summary Action 测试
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { SummaryModal } from "../SummaryModal";
import { useDiscussionStore } from "../../stores/discussionStore";

// Mock fetch
globalThis.fetch = vi.fn();

describe("SummaryModal", () => {
  beforeEach(() => {
    useDiscussionStore.getState().reset();
    vi.clearAllMocks();
  });

  it("renders generate button when no summary exists", () => {
    useDiscussionStore.getState().initDiscussion(
      { id: "d1", topic: "测试", status: "finished", round_count: 3, max_rounds: 5 },
      []
    );

    render(<SummaryModal />);
    expect(screen.getByTestId("generate-summary-btn")).toBeInTheDocument();
    expect(screen.getByText("📝 生成总结")).toBeInTheDocument();
  });

  it("shows loading state when summarizing", () => {
    useDiscussionStore.setState({ isSummarizing: true });

    render(<SummaryModal />);
    expect(screen.getByTestId("summary-loading")).toBeInTheDocument();
    expect(
      screen.getByText("主持人正在撰写总结，请稍候...")
    ).toBeInTheDocument();
  });

  it("shows error state with retry button", () => {
    useDiscussionStore.setState({
      summaryError: "LLM 调用超时",
      isSummarizing: false,
    });

    render(<SummaryModal />);
    expect(screen.getByTestId("summary-error")).toBeInTheDocument();
    expect(screen.getByText(/LLM 调用超时/)).toBeInTheDocument();
  });

  it("shows summary content when available", () => {
    useDiscussionStore.setState({
      summary: {
        id: "s1",
        content: "## 讨论总结\n\n这是一段精彩的总结。\n\n- 发现1\n- 发现2",
        discussion_id: "d1",
      },
    });

    render(<SummaryModal />);
    expect(screen.getByTestId("summary-content")).toBeInTheDocument();
    expect(screen.getByText(/精彩的总结/)).toBeInTheDocument();
  });
});

describe("discussionStore summary actions", () => {
  beforeEach(() => {
    useDiscussionStore.getState().reset();
    vi.clearAllMocks();
  });

  it("generateSummary sets isSummarizing and summary on success", async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "s1",
        content: "总结内容",
        discussion_id: "d1",
      }),
    });

    useDiscussionStore.getState().initDiscussion(
      { id: "d1", topic: "T", status: "finished", round_count: 3 },
      []
    );

    await useDiscussionStore.getState().generateSummary("d1");

    const state = useDiscussionStore.getState();
    expect(state.isSummarizing).toBe(false);
    expect(state.summary.content).toBe("总结内容");
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/discussions/d1/summarize",
      { method: "POST" }
    );
  });

  it("generateSummary sets error on failure", async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: { message: "服务器错误" } }),
    });

    await useDiscussionStore.getState().generateSummary("d1");

    const state = useDiscussionStore.getState();
    expect(state.isSummarizing).toBe(false);
    expect(state.summaryError).toBe("服务器错误");
    expect(state.summary).toBeNull();
  });
});
