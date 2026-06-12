/**
 * discussionStore 状态管理测试
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useDiscussionStore } from "../../stores/discussionStore";

describe("discussionStore", () => {
  beforeEach(() => {
    useDiscussionStore.getState().reset();
  });

  it("initDiscussion sets meta and guests", () => {
    useDiscussionStore.getState().initDiscussion(
      { id: "d1", topic: "测试", status: "active", round_count: 0, max_rounds: 10 },
      [
        { id: "g1", role: "host", name: "主持人", color: "#E8A840" },
        { id: "g2", role: "expert", name: "专家1", color: "#4A90D9" },
      ]
    );

    const state = useDiscussionStore.getState();
    expect(state.meta.id).toBe("d1");
    expect(state.meta.topic).toBe("测试");
    expect(state.guests).toHaveLength(2);
    expect(state.guests[0].name).toBe("主持人");
    expect(state.guests[0].snapshot).toBeNull();
  });

  it("onGuestStatusChange updates guest status", () => {
    useDiscussionStore.getState().initDiscussion(
      { id: "d1", topic: "T", status: "active", round_count: 0, max_rounds: null },
      [{ id: "g1", role: "host", name: "H", status: "idle" }]
    );

    useDiscussionStore.getState().onGuestStatusChange({
      discussion_id: "d1",
      guest_id: "g1",
      status: "speaking",
    });

    expect(useDiscussionStore.getState().guests[0].status).toBe("speaking");
  });

  it("onSnapshotUpdate sets snapshot on guest", () => {
    useDiscussionStore.getState().initDiscussion(
      { id: "d1", topic: "T", status: "active", round_count: 0, max_rounds: null },
      [{ id: "g1", role: "expert", name: "E", status: "thinking" }]
    );

    useDiscussionStore.getState().onSnapshotUpdate({
      discussion_id: "d1",
      guest_id: "g1",
      public_thought: "正在思考...",
      confidence: 0.85,
      intent: "raise_hand",
      status: "thinking",
    });

    const guest = useDiscussionStore.getState().guests[0];
    expect(guest.snapshot).toEqual({
      public_thought: "正在思考...",
      confidence: 0.85,
      intent: "raise_hand",
    });
  });

  it("onTranscriptAppend adds finalized message", () => {
    useDiscussionStore.getState().onTranscriptAppend({
      id: "te1",
      guest_id: "g1",
      guest_name: "张明远",
      guest_color: "#E8A840",
      guest_role: "host",
      guest_title: "主持人",
      sequence_number: 1,
      round_number: 1,
      entry_type: "opening_statement",
      content: "欢迎各位。",
    });

    const msgs = useDiscussionStore.getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].content).toBe("欢迎各位。");
    expect(msgs[0].is_final).toBe(true);
  });

  it("onTranscriptDelta accumulates streaming content", () => {
    useDiscussionStore.getState().onTranscriptDelta({
      entry_id: "stream-1",
      guest_id: "g1",
      guest_name: "李",
      guest_color: "#4A90D9",
      sequence_number: 1,
      content: "我认",
    });

    expect(useDiscussionStore.getState().streamingId).toBe("stream-1");

    useDiscussionStore.getState().onTranscriptDelta({
      entry_id: "stream-1",
      guest_id: "g1",
      guest_name: "李",
      guest_color: "#4A90D9",
      sequence_number: 1,
      content: "为这",
    });

    const msg = useDiscussionStore.getState().messages[0];
    expect(msg.content).toBe("我认为这");
    expect(msg.is_final).toBe(false);
  });

  it("onTranscriptAppend replaces delta entry", () => {
    // 先来几条 delta
    useDiscussionStore.getState().onTranscriptDelta({
      entry_id: "tmp-1", guest_id: "g1", guest_name: "X",
      guest_color: "#aaa", sequence_number: 1, content: "AAA",
    });

    // 最后 append 替换
    useDiscussionStore.getState().onTranscriptAppend({
      id: "tmp-1",
      guest_id: "g1",
      guest_name: "X",
      guest_color: "#aaa",
      sequence_number: 1,
      content: "完整发言内容",
      is_final: true,
    });

    const msgs = useDiscussionStore.getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].is_final).toBe(true);
    expect(msgs[0].content).toBe("完整发言内容");
    expect(useDiscussionStore.getState().streamingId).toBeNull();
  });

  it("onConsensusUpdate replaces consensus list", () => {
    useDiscussionStore.getState().onConsensusUpdate({
      items: [
        { id: "c1", content: "共识1", agreed_guests: ["g1"], confidence: 0.8 },
      ],
    });
    expect(useDiscussionStore.getState().consensus).toHaveLength(1);
  });

  it("onDiscussionStatusChange updates meta status", () => {
    useDiscussionStore.getState().initDiscussion(
      { id: "d1", topic: "T", status: "active", round_count: 0, max_rounds: null },
      []
    );

    useDiscussionStore.getState().onDiscussionStatusChange({
      discussion_id: "d1",
      status: "summarizing",
    });

    expect(useDiscussionStore.getState().meta.status).toBe("summarizing");
  });

  it("onRoundAdvance updates roundCount", () => {
    useDiscussionStore.getState().initDiscussion(
      { id: "d1", topic: "T", status: "active", round_count: 0, max_rounds: 10 },
      []
    );

    useDiscussionStore.getState().onRoundAdvance({
      round_number: 3,
    });

    expect(useDiscussionStore.getState().meta.roundCount).toBe(3);
  });

  it("reset clears all state", () => {
    useDiscussionStore.getState().initDiscussion(
      { id: "d1", topic: "T", status: "active", round_count: 1, max_rounds: 5 },
      [{ id: "g1", role: "host", name: "H" }]
    );
    useDiscussionStore.getState().onTranscriptAppend({
      id: "te1", guest_id: "g1", sequence_number: 1, content: "xxx",
    });

    useDiscussionStore.getState().reset();

    const s = useDiscussionStore.getState();
    expect(s.meta.id).toBeNull();
    expect(s.guests).toHaveLength(0);
    expect(s.messages).toHaveLength(0);
    expect(s.consensus).toHaveLength(0);
    expect(s.divergences).toHaveLength(0);
    expect(s.streamingId).toBeNull();
  });
});
