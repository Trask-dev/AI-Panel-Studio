/**
 * discussionStore — 讨论状态管理 (Zustand)
 *
 * 管理:
 *   - guests:        嘉宾列表 (含 status/snapshot)
 *   - messages:      发言记录 (TranscriptEntry[])
 *   - consensus:     共识项列表
 *   - divergences:   分歧项列表
 *   - meta:          讨论元信息 (topic, status, round_count, ...)
 *   - streamingId:   当前流式输出中的 entry_id (用于光标渲染)
 *
 * Actions 对应 SSE 事件:
 *   onSnapshotUpdate / onTranscriptAppend / onConsensusUpdate ...
 */

import { create } from "zustand";

export const useDiscussionStore = create((set, get) => ({
  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  meta: {
    id: null,
    topic: "",
    status: "setup",
    roundCount: 0,
    maxRounds: null,
  },
  guests: [],
  messages: [],
  consensus: [],
  divergences: [],
  streamingId: null,

  // -----------------------------------------------------------------------
  // 初始化讨论
  // -----------------------------------------------------------------------
  initDiscussion(discussion, guestList) {
    set({
      meta: {
        id: discussion.id,
        topic: discussion.topic,
        status: discussion.status,
        roundCount: discussion.round_count,
        maxRounds: discussion.max_rounds,
      },
      guests: guestList.map((g) => ({ ...g, snapshot: null })),
      messages: [],
      consensus: [],
      divergences: [],
      streamingId: null,
    });
  },

  // -----------------------------------------------------------------------
  // SSE 事件处理
  // -----------------------------------------------------------------------

  onGuestStatusChange(payload) {
    const { guest_id, status } = payload;
    set((s) => ({
      guests: s.guests.map((g) =>
        g.id === guest_id ? { ...g, status } : g
      ),
    }));
  },

  onSnapshotUpdate(payload) {
    const { guest_id, public_thought, confidence, intent, status } = payload;
    set((s) => ({
      guests: s.guests.map((g) =>
        g.id === guest_id
          ? {
              ...g,
              status: status || g.status,
              snapshot: { public_thought, confidence, intent },
            }
          : g
      ),
    }));
  },

  onTranscriptDelta(payload) {
    const { entry_id, content, guest_id, guest_name, guest_color, sequence_number } =
      payload;
    const existing = get().messages.find((m) => m.id === entry_id);

    set((s) => {
      if (existing) {
        return {
          streamingId: entry_id,
          messages: s.messages.map((m) =>
            m.id === entry_id ? { ...m, content: m.content + content } : m
          ),
        };
      }
      // 新流式消息
      return {
        streamingId: entry_id,
        messages: [
          ...s.messages,
          {
            id: entry_id,
            guest_id,
            guest_name: guest_name || "",
            guest_color: guest_color || "#9090a0",
            sequence_number,
            content,
            entry_type: payload.entry_type || "speech",
            is_final: false,
          },
        ],
      };
    });
  },

  onTranscriptAppend(payload) {
    set((s) => ({
      streamingId: null,
      messages: s.messages
        .filter((m) => m.id !== payload.id) // 移除 delta 阶段的临时条目
        .concat({
          id: payload.id,
          guest_id: payload.guest_id,
          guest_name: payload.guest_name || "",
          guest_color: payload.guest_color || "#9090a0",
          guest_role: payload.guest_role || "expert",
          guest_title: payload.guest_title || "",
          sequence_number: payload.sequence_number,
          round_number: payload.round_number || 0,
          entry_type: payload.entry_type || "speech",
          content: payload.content,
          is_final: true,
          spoken_at: payload.spoken_at || "",
          quote_of: payload.quote_of || null,
        })
        .sort((a, b) => a.sequence_number - b.sequence_number),
    }));
  },

  onConsensusUpdate(payload) {
    set({ consensus: payload.items || [] });
  },

  onDivergenceUpdate(payload) {
    set({ divergences: payload.items || [] });
  },

  onDiscussionStatusChange(payload) {
    set((s) => ({
      meta: { ...s.meta, status: payload.status },
    }));
  },

  onRoundAdvance(payload) {
    set((s) => ({
      meta: { ...s.meta, roundCount: payload.round_number },
    }));
  },

  // -----------------------------------------------------------------------
  // 批量加载历史消息
  // -----------------------------------------------------------------------
  loadHistory(entries) {
    set({
      messages: entries.map((e) => ({
        ...e,
        is_final: true,
      })),
    });
  },

  // -----------------------------------------------------------------------
  // 讨论总结
  // -----------------------------------------------------------------------
  summary: null,
  isSummarizing: false,
  summaryError: null,

  async generateSummary(discussionId) {
    set({ isSummarizing: true, summaryError: null });
    try {
      const resp = await fetch(
        `/api/v1/discussions/${discussionId}/summarize`,
        { method: "POST" }
      );
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error?.message || "总结生成失败");
      }
      const data = await resp.json();
      set({ summary: data, isSummarizing: false });
    } catch (e) {
      set({ summaryError: e.message, isSummarizing: false });
    }
  },

  setSummary(summary) {
    set({ summary });
  },

  // -----------------------------------------------------------------------
  // Reset
  // -----------------------------------------------------------------------
  reset() {
    set({
      meta: { id: null, topic: "", status: "setup", roundCount: 0, maxRounds: null },
      guests: [],
      messages: [],
      consensus: [],
      divergences: [],
      streamingId: null,
      summary: null,
      isSummarizing: false,
      summaryError: null,
    });
  },
}));
