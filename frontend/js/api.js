/**
 * PaperFetch V2 - API Client
 */
const API_BASE = window.location.origin;

const API = {
  async detectPapers(inputs) {
    const res = await fetch(`${API_BASE}/api/papers/detect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ inputs }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Detection failed' }));
      throw new Error(err.detail || 'Failed to detect papers');
    }
    return await res.json();
  },

  async getPaper(paperId) {
    const res = await fetch(`${API_BASE}/api/papers/${paperId}`);
    if (!res.ok) throw new Error('Failed to fetch paper');
    return await res.json();
  },

  async updatePaper(paperId, data) {
    const res = await fetch(`${API_BASE}/api/papers/${paperId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update paper metadata');
    return await res.json();
  },

  async createDownloadJobs(paperIds, forceDownload = false) {
    const res = await fetch(`${API_BASE}/api/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper_ids: paperIds, force_download: forceDownload }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Job creation failed' }));
      throw new Error(err.detail || 'Failed to start download');
    }
    return await res.json();
  },

  async getJobs() {
    const res = await fetch(`${API_BASE}/api/jobs`);
    if (!res.ok) throw new Error('Failed to fetch jobs');
    return await res.json();
  },

  async retryJob(jobId) {
    const res = await fetch(`${API_BASE}/api/jobs/${jobId}/retry`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to retry job');
    return await res.json();
  },

  async cancelJob(jobId) {
    const res = await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to cancel job');
    return await res.json();
  },

  async cancelAllJobs() {
    const res = await fetch(`${API_BASE}/api/jobs`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to cancel all jobs');
    return await res.json();
  },

  async getLibrary(params = {}) {
    const qs = new URLSearchParams(params).toString();
    const res = await fetch(`${API_BASE}/api/library?${qs}`);
    if (!res.ok) throw new Error('Failed to fetch library');
    return await res.json();
  },

  async deletePaper(paperId) {
    const res = await fetch(`${API_BASE}/api/library/${paperId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete paper');
    return await res.json();
  },

  async getHistory() {
    const res = await fetch(`${API_BASE}/api/history`);
    if (!res.ok) throw new Error('Failed to fetch history');
    return await res.json();
  },

  async getStats() {
    const res = await fetch(`${API_BASE}/api/dashboard/stats`);
    if (!res.ok) throw new Error('Failed to fetch stats');
    return await res.json();
  },

  async getSingleBibtex(paperId) {
    const res = await fetch(`${API_BASE}/api/citations/paper/${paperId}`);
    if (!res.ok) throw new Error('Failed to fetch BibTeX');
    return await res.text();
  },

  async exportBibtex(paperIds) {
    const res = await fetch(`${API_BASE}/api/citations/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper_ids: paperIds }),
    });
    if (!res.ok) throw new Error('Failed to export citations');
    return await res.text();
  },

  async getSettings() {
    const res = await fetch(`${API_BASE}/api/settings`);
    if (!res.ok) throw new Error('Failed to fetch settings');
    return await res.json();
  },

  async updateSettings(data) {
    const res = await fetch(`${API_BASE}/api/settings`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update settings');
    return await res.json();
  },
};
