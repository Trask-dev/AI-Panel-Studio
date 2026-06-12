/**
 * API Service — 封装所有后端 API 调用。
 *
 * 所有接口的 URL、方法、参数严格对应后端 app/api/discussions.py。
 */

const BASE = "/api/v1";

// ---------------------------------------------------------------------------
// 讨论
// ---------------------------------------------------------------------------

/** POST /discussions */
export async function createDiscussion({ topic, expertCount = 3 }) {
  const resp = await fetch(`${BASE}/discussions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic,
      expert_count: expertCount,
      host_style: "socratic",
      llm_model: "deepseek-chat",
      interjection_mode: "moderated",
    }),
  });
  return resp.json();
}

/** GET /discussions */
export async function listDiscussions(status) {
  const url = status
    ? `${BASE}/discussions?status=${status}`
    : `${BASE}/discussions`;
  const resp = await fetch(url);
  return resp.json();
}

/** GET /discussions/{id} */
export async function getDiscussion(id) {
  const resp = await fetch(`${BASE}/discussions/${id}`);
  return resp.json();
}

// ---------------------------------------------------------------------------
// 嘉宾
// ---------------------------------------------------------------------------

/** POST /discussions/{id}/guests/generate */
export async function generateGuests(id) {
  const resp = await fetch(`${BASE}/discussions/${id}/guests/generate`, {
    method: "POST",
  });
  return resp.json();
}

// ---------------------------------------------------------------------------
// 讨论控制
// ---------------------------------------------------------------------------

/** POST /discussions/{id}/start */
export async function startDiscussion(id) {
  const resp = await fetch(`${BASE}/discussions/${id}/start`, {
    method: "POST",
  });
  return resp.json();
}

/** POST /discussions/{id}/rounds/next */
export async function advanceRound(id) {
  const resp = await fetch(`${BASE}/discussions/${id}/rounds/next`, {
    method: "POST",
  });
  return resp.json();
}

/** POST /discussions/{id}/end */
export async function endDiscussion(id, force = false) {
  const url = force
    ? `${BASE}/discussions/${id}/end?force=true`
    : `${BASE}/discussions/${id}/end`;
  const resp = await fetch(url, { method: "POST" });
  return resp.json();
}

// ---------------------------------------------------------------------------
// 数据查询
// ---------------------------------------------------------------------------

/** GET /discussions/{id}/messages */
export async function fetchMessages(id, cursor = 0, limit = 50) {
  const resp = await fetch(
    `${BASE}/discussions/${id}/messages?cursor=${cursor}&limit=${limit}`
  );
  return resp.json();
}

/** GET /discussions/{id}/consensus */
export async function fetchConsensus(id) {
  const resp = await fetch(`${BASE}/discussions/${id}/consensus`);
  return resp.json();
}

/** GET /discussions/{id}/divergences */
export async function fetchDivergences(id) {
  const resp = await fetch(`${BASE}/discussions/${id}/divergences`);
  return resp.json();
}

/** POST /discussions/{id}/summarize */
export async function generateSummary(id) {
  const resp = await fetch(`${BASE}/discussions/${id}/summarize`, {
    method: "POST",
  });
  return resp.json();
}

/** GET /discussions/{id}/summary */
export async function fetchSummary(id) {
  const resp = await fetch(`${BASE}/discussions/${id}/summary`);
  return resp.json();
}

// ---------------------------------------------------------------------------
// SSE
// ---------------------------------------------------------------------------

/** GET /discussions/{id}/events → EventSource */
export function connectSSE(id) {
  return new EventSource(`${BASE}/discussions/${id}/events`);
}
