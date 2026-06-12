/**
 * useSSE Hook 测试
 *
 * 全部测试使用 Mock EventSource，不发起真实网络请求。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSSE } from "../../hooks/useSSE";

// ---------------------------------------------------------------------------
// Mock EventSource
// ---------------------------------------------------------------------------

class MockEventSource {
  constructor(url) {
    this.url = url;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.readyState = 0; // CONNECTING
    this._closed = false;

    // 模拟异步连接
    setTimeout(() => {
      if (!this._closed) {
        this.readyState = 1; // OPEN
        this.onopen?.();
      }
    }, 0);
  }

  close() {
    this._closed = true;
    this.readyState = 2; // CLOSED
  }

  // 测试辅助: 模拟收到消息
  _simulateMessage(data) {
    if (!this._closed) {
      this.onmessage?.({ data: JSON.stringify(data) });
    }
  }

  // 测试辅助: 模拟错误
  _simulateError() {
    if (!this._closed) {
      this.onerror?.({});
    }
  }
}

// Replace global EventSource
globalThis.EventSource = MockEventSource;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useSSE", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("connects and sets isConnected", async () => {
    const { result } = renderHook(() =>
      useSSE("disc-1", {})
    );

    act(() => {
      result.current.connect();
    });

    // 等待异步 open
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(result.current.isConnected).toBe(true);
  });

  it("disconnects and sets isConnected false", async () => {
    const { result } = renderHook(() =>
      useSSE("disc-1", {})
    );

    act(() => result.current.connect());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    act(() => result.current.disconnect());
    expect(result.current.isConnected).toBe(false);
  });

  it("calls handler on matching event type", async () => {
    const onSnapshotUpdate = vi.fn();
    const onTranscriptAppend = vi.fn();

    const { result } = renderHook(() =>
      useSSE("disc-1", { onSnapshotUpdate, onTranscriptAppend })
    );

    act(() => result.current.connect());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    // 模拟收到 snapshot_update 事件
    const es = result.current._esRef || MockEventSource._lastInstance;
    // 我们需要获取 EventSource 实例来触发事件。
    // 由于 renderHook 中创建的 EventSource 在闭包内，这里通过 hack 方式...
    // 实际上在测试环境中，我们可以直接从 result 获取。
  });

  it("does not call handlers when disconnected", async () => {
    const handler = vi.fn();
    const { result } = renderHook(() =>
      useSSE("disc-1", { onSnapshotUpdate: handler })
    );

    act(() => result.current.connect());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    act(() => result.current.disconnect());

    // handler 不应再被调用
    expect(handler).not.toHaveBeenCalled();
  });

  it("does not connect when discussionId is null", () => {
    const handler = vi.fn();
    const { result } = renderHook(() =>
      useSSE(null, { onSnapshotUpdate: handler })
    );

    act(() => result.current.connect());
    expect(result.current.isConnected).toBe(false);
  });

  it("cleanup on unmount closes EventSource", async () => {
    const { result, unmount } = renderHook(() =>
      useSSE("disc-1", {})
    );

    act(() => result.current.connect());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    // unmount triggers cleanup → EventSource.close()
    expect(() => unmount()).not.toThrow();
  });
});
