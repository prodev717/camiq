/** Centralised API helpers — all calls go through here */

const BASE = 'http://localhost:8000';

export async function startIndexing(videoPath) {
  const res = await fetch(`${BASE}/index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_path: videoPath }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to start indexing');
  }
  return res.json();
}

export async function getIndexStatus() {
  const res = await fetch(`${BASE}/index/status`);
  if (!res.ok) throw new Error('Failed to fetch status');
  return res.json();
}

export async function searchQuery(query, topK = 5) {
  const res = await fetch(`${BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k: topK }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Search failed');
  }
  return res.json();
}

export function frameUrl(frameIndex) {
  return `${BASE}/frame/${frameIndex}`;
}

export function videoStreamUrl() {
  return `${BASE}/video/stream`;
}
