/**
 * TranscriptPanel 组件测试
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { TranscriptPanel } from "../TranscriptPanel";

const makeMsg = (id, overrides = {}) => ({
  id,
  guest_id: "g1",
  guest_name: "张明远",
  guest_color: "#E8A840",
  guest_title: "主持人",
  sequence_number: 1,
  round_number: 1,
  entry_type: "opening_statement",
  content: "欢迎各位来到今天的圆桌讨论。",
  is_final: true,
  ...overrides,
});

describe("TranscriptPanel", () => {
  it("renders empty state when no messages", () => {
    render(<TranscriptPanel messages={[]} />);
    expect(screen.getByTestId("transcript-empty")).toBeInTheDocument();
    expect(screen.getByText("等待讨论开始...")).toBeInTheDocument();
  });

  it("renders message entries with speaker names", () => {
    const messages = [
      makeMsg("1", { guest_name: "张明远", entry_type: "opening_statement" }),
      makeMsg("2", { guest_name: "李思涵", guest_color: "#4A90D9", entry_type: "speech" }),
    ];

    render(<TranscriptPanel messages={messages} />);
    expect(screen.getByText("张明远")).toBeInTheDocument();
    expect(screen.getByText("李思涵")).toBeInTheDocument();
    expect(screen.getByText("opening_statement")).toBeInTheDocument();
  });

  it("renders streaming entry with cursor and badge", () => {
    const messages = [
      makeMsg("stream-1", {
        content: "我需要纠正一个认知偏差。",
        is_final: false,
      }),
    ];

    render(<TranscriptPanel messages={messages} streamingId="stream-1" />);
    expect(screen.getByTestId("streaming-badge")).toBeInTheDocument();
    // 检查内容包含光标
    const content = screen.getByTestId("entry-content");
    expect(content.textContent).toContain("█");
  });

  it("renders round dividers for multi-round conversations", () => {
    const messages = [
      makeMsg("1", { round_number: 1 }),
      makeMsg("2", { round_number: 2 }),
      makeMsg("3", { round_number: 2 }),
    ];

    render(<TranscriptPanel messages={messages} />);
    const dividers = screen.getAllByTestId("round-divider");
    expect(dividers.length).toBe(1); // 只有 Round 2 需要分隔线
    expect(dividers[0].textContent).toContain("第 2 轮");
  });

  it("renders entry bar with correct guest color", () => {
    const messages = [
      makeMsg("1", { guest_color: "#E8A840" }),
    ];

    render(<TranscriptPanel messages={messages} />);
    const bar = screen.getByTestId("entry-bar");
    expect(bar).toHaveStyle({ backgroundColor: "#E8A840" });
  });

  it("falls back to guest lookup when color missing on message", () => {
    const messages = [
      makeMsg("1", { guest_color: undefined }),
    ];
    const guests = [{ id: "g1", color: "#50B86C" }];

    render(<TranscriptPanel messages={messages} guests={guests} />);
    const bar = screen.getByTestId("entry-bar");
    expect(bar).toHaveStyle({ backgroundColor: "#50B86C" });
  });
});
