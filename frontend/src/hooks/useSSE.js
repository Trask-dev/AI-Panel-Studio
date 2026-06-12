/**
 * useSSE — Server-Sent Events 通信 Hook
 *
 * 职责:
 *   1. 建立与后端的 EventSource 连接
 *   2. 按 event.type 分发到注册的回调
 *   3. 自动重连 + cleanup
 *   4. 支持 after_sequence 断线续传
 *
 * 用法:
 *   const { connect, disconnect, isConnected } = useSSE(discussionId, {
 *     onSnapshotUpdate: (payload) => { ... },
 *     onTranscriptAppend: (payload) => { ... },
 *     ...
 *   });
 */

import { useRef, useCallback, useEffect, useState } from "react";

const EVENT_HANDLERS = [
  "guestStatusChange",
  "snapshotUpdate",
  "transcriptDelta",
  "transcriptAppend",
  "consensusUpdate",
  "divergenceUpdate",
  "roundAdvance",
  "discussionStatusChange",
  "error",
];

/**
 * @param {string|null} discussionId
 * @param {Object} handlers — { onGuestStatusChange, onSnapshotUpdate, ... }
 * @returns {{ connect: Function, disconnect: Function, isConnected: boolean }}
 */
export function useSSE(discussionId, handlers = {}) {
  const esRef = useRef(null);
  const [isConnected, setIsConnected] = useState(false);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  const disconnect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
      setIsConnected(false);
    }
  }, []);

  const connect = useCallback(
    (afterSequence) => {
      if (!discussionId) return;
      disconnect();

      let url = `/api/v1/discussions/${discussionId}/events`;
      if (afterSequence != null) {
        url += `?after_sequence=${afterSequence}`;
      }

      const es = new EventSource(url);
      esRef.current = es;

      es.onopen = () => setIsConnected(true);

      es.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data);
          const handlerKey = mapEventToHandler(event.type);
          if (handlerKey && handlersRef.current[handlerKey]) {
            handlersRef.current[handlerKey](event.payload);
          }
        } catch {
          // 解析失败则忽略 (非 JSON 数据如 heartbeat)
        }
      };

      es.onerror = () => {
        setIsConnected(false);
        // EventSource 自动重连; 如需自定义重连逻辑可在此处理
      };
    },
    [discussionId, disconnect]
  );

  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
        setIsConnected(false);
      }
    };
  }, []);

  return { connect, disconnect, isConnected };
}

// ---------------------------------------------------------------------------
// 事件类型 → handler key 映射
// ---------------------------------------------------------------------------
function mapEventToHandler(type) {
  const map = {
    guest_status_change: "onGuestStatusChange",
    snapshot_update: "onSnapshotUpdate",
    transcript_delta: "onTranscriptDelta",
    transcript_append: "onTranscriptAppend",
    consensus_update: "onConsensusUpdate",
    divergence_update: "onDivergenceUpdate",
    round_advance: "onRoundAdvance",
    discussion_status_change: "onDiscussionStatusChange",
    error: "onError",
    heartbeat: null,
  };
  return map[type] || null;
}
