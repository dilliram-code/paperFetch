/**
 * PaperFetch V2 - Real-Time Download Dashboard & SSE Progress Stream
 */

let eventSource = null;
const activeJobs = new Map();

function initSSEProgress() {
  if (eventSource) return;

  eventSource = new EventSource('/api/jobs/stream/all');

  eventSource.addEventListener('progress', (e) => {
    try {
      const job = JSON.parse(e.data);
      updateJobCard(job);
    } catch (err) {
      console.error('SSE JSON error', err);
    }
  });

  eventSource.onerror = () => {
    // Reconnects automatically by browser standard EventSource
  };
}

function updateJobCard(job) {
  const container = document.getElementById('active-downloads-list');
  if (!container) return;

  activeJobs.set(job.id, job);

  let card = document.getElementById(`job-card-${job.id}`);
  if (!card) {
    card = document.createElement('div');
    card.id = `job-card-${job.id}`;
    card.className = 'glass-panel download-card';
    container.prepend(card);
  }

  const isCompleted = job.status === 'completed';
  const isFailed = job.status === 'failed';
  const isCancelled = job.status === 'cancelled';

  let statusBadge = `<span class="badge badge-info">${escapeHtml(job.status)}</span>`;
  if (isCompleted) {
    statusBadge = '<span class="badge badge-success">Completed</span>';
  } else if (isFailed) {
    statusBadge = `<span class="badge badge-danger">Failed</span>`;
  } else if (isCancelled) {
    statusBadge = '<span class="badge badge-warning">Cancelled</span>';
  }

  const percent = job.progress_percent || (isCompleted ? 100 : 0);
  const downloadedStr = formatBytes(job.downloaded_bytes || 0);
  const totalStr = job.total_bytes > 0 ? formatBytes(job.total_bytes) : 'Unknown size';
  const speedStr = job.speed_bytes_per_sec > 0 ? `${formatBytes(job.speed_bytes_per_sec)}/s` : '--';
  const etaStr = job.eta_seconds > 0 ? `${Math.ceil(job.eta_seconds)}s remaining` : '';

  card.innerHTML = `
    <div class="download-card-header">
      <div style="flex: 1;">
        <div style="font-weight: 600; font-size: 15px; color: #fff;">${escapeHtml(
          job.title || job.filename || 'Research Paper'
        )}</div>
        <div style="font-size: 12px; color: var(--text-dim); margin-top: 4px;">
          ${escapeHtml(job.filename || '')}
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        ${statusBadge}
        ${
          !isCompleted && !isFailed && !isCancelled
            ? `<button class="btn btn-danger btn-sm" onclick="cancelDownloadJob('${job.id}')">Cancel</button>`
            : ''
        }
        ${
          isFailed
            ? `<button class="btn btn-secondary btn-sm" onclick="retryDownloadJob('${job.id}')">Retry</button>`
            : ''
        }
        ${
          isCompleted && job.paper_id
            ? `<a href="/api/papers/${job.paper_id}/download" download class="btn btn-primary btn-sm">Download PDF</a>`
            : ''
        }
      </div>
    </div>

    <div class="progress-track">
      <div class="progress-fill ${isCompleted ? 'completed' : ''} ${isFailed ? 'failed' : ''}" style="width: ${percent}%;"></div>
    </div>

    <div class="download-stats">
      <span>${percent}% (${downloadedStr} / ${totalStr})</span>
      <span>${isCompleted ? 'Validated & Organized' : isFailed ? (escapeHtml(job.error_message) || 'Error') : `${speedStr} &bull; ${etaStr}`}</span>
    </div>
  `;
}

async function cancelDownloadJob(jobId) {
  try {
    await API.cancelJob(jobId);
    showToast('Download cancelled', 'info');
  } catch (err) {
    showToast(err.message, 'danger');
  }
}

async function retryDownloadJob(jobId) {
  try {
    await API.retryJob(jobId);
    showToast('Retrying download...', 'info');
  } catch (err) {
    showToast(err.message, 'danger');
  }
}

async function cancelAllActiveJobs() {
  try {
    const res = await API.cancelAllJobs();
    showToast(`Cancelled ${res.cancelled_count} active jobs`, 'info');
  } catch (err) {
    showToast(err.message, 'danger');
  }
}

async function downloadCurrentBatchZip() {
  let batchIds = window.currentBatchPaperIds || [];
  if (!batchIds || batchIds.length === 0) {
    try {
      const stored = sessionStorage.getItem('currentBatchPaperIds');
      if (stored) batchIds = JSON.parse(stored);
    } catch (e) {}
  }

  if (!batchIds || batchIds.length === 0) {
    showToast('No active batch detected. Please paste URLs to detect and download papers first.', 'warning');
    return;
  }

  showToast('Preparing Batch ZIP for current papers...', 'info');

  try {
    const query = batchIds.map((id) => `paper_ids=${encodeURIComponent(id)}`).join('&');
    const resp = await fetch(`/api/downloads/zip?${query}`);

    if (!resp.ok) {
      let errorMsg = 'Failed to download batch ZIP';
      try {
        const errJson = await resp.json();
        errorMsg = errJson.detail || errorMsg;
      } catch (e) {}
      showToast(errorMsg, 'warning');
      return;
    }

    const blob = await resp.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = 'PaperFetch_Batch.zip';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(blobUrl);
    showToast('Batch ZIP downloaded successfully!', 'success');
  } catch (err) {
    showToast(`Error downloading ZIP: ${err.message}`, 'danger');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initSSEProgress();

  const btnCancelAll = document.getElementById('btn-cancel-all');
  if (btnCancelAll) {
    btnCancelAll.addEventListener('click', cancelAllActiveJobs);
  }

  const btnDownloadZip = document.getElementById('btn-download-zip');
  if (btnDownloadZip) {
    btnDownloadZip.addEventListener('click', downloadCurrentBatchZip);
  }

  const topBtnZip = document.getElementById('top-btn-zip');
  if (topBtnZip) {
    topBtnZip.addEventListener('click', (e) => {
      e.preventDefault();
      downloadCurrentBatchZip();
    });
  }
});
