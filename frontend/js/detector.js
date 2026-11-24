/**
 * PaperFetch V2 - Input parsing, validation, detection, and metadata preview
 */

let detectedPapers = [];
let selectedPaperIds = new Set();

document.addEventListener('DOMContentLoaded', () => {
  const urlInput = document.getElementById('url-input');
  const inputCounter = document.getElementById('input-counter');
  const btnDetect = document.getElementById('btn-detect');
  const btnClear = document.getElementById('btn-clear');
  const btnStartDownload = document.getElementById('btn-start-download');
  const previewSection = document.getElementById('preview-section');
  const previewList = document.getElementById('preview-list');

  if (!urlInput) return;

  function updateCounter() {
    const lines = urlInput.value
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    const count = lines.length;
    inputCounter.textContent = `${count} / 10 papers`;
    if (count > 10) {
      inputCounter.style.color = 'var(--accent-rose)';
      inputCounter.style.borderColor = 'rgba(244, 63, 94, 0.4)';
    } else {
      inputCounter.style.color = 'var(--accent-cyan)';
      inputCounter.style.borderColor = 'rgba(6, 182, 212, 0.25)';
    }
  }

  urlInput.addEventListener('input', updateCounter);

  if (btnClear) {
    btnClear.addEventListener('click', () => {
      urlInput.value = '';
      updateCounter();
      if (previewSection) previewSection.style.display = 'none';
      detectedPapers = [];
      selectedPaperIds.clear();
      window.currentBatchPaperIds = [];
      sessionStorage.removeItem('currentBatchPaperIds');
    });
  }

  if (btnDetect) {
    btnDetect.addEventListener('click', async () => {
      const lines = urlInput.value
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => l.length > 0);

      if (lines.length === 0) {
        showToast('Please enter at least one URL or DOI', 'warning');
        return;
      }

      if (lines.length > 10) {
        showToast('Maximum 10 papers allowed per batch. Please trim input.', 'danger');
        return;
      }

      btnDetect.disabled = true;
      btnDetect.innerHTML = '<span class="status-dot"></span> Analyzing & Extracting...';

      try {
        const resp = await API.detectPapers(lines);
        detectedPapers = resp.papers || [];
        selectedPaperIds = new Set(
          detectedPapers.filter((p) => p.pdf_accessible).map((p) => p.id)
        );
        window.currentBatchPaperIds = detectedPapers.map((p) => p.id);
        sessionStorage.setItem('currentBatchPaperIds', JSON.stringify(window.currentBatchPaperIds));

        renderPreviewCards(detectedPapers);
        if (previewSection) previewSection.style.display = 'block';
        showToast(`Discovered ${detectedPapers.length} paper(s)`, 'success');
      } catch (err) {
        showToast(err.message, 'danger');
      } finally {
        btnDetect.disabled = false;
        btnDetect.innerHTML = 'Detect & Preview';
      }
    });
  }

  function renderPreviewCards(papers) {
    if (!previewList) return;
    previewList.innerHTML = '';

    papers.forEach((p) => {
      const card = document.createElement('div');
      const isDup = p.duplicate_info && p.duplicate_info.is_duplicate;
      const isAccessible = p.pdf_accessible;

      card.className = `glass-panel preview-card ${isDup ? 'duplicate' : ''} ${
        !isAccessible ? 'inaccessible' : ''
      }`;
      card.id = `preview-${p.id}`;

      const authorsStr = (p.authors && p.authors.length > 0) ? p.authors.join(', ') : 'Unknown Authors';
      const yearStr = p.year ? p.year : 'Date n/a';
      const venueStr = p.journal_or_conference || p.publisher || 'Preprint / Academic Webpage';

      let duplicateBadge = '';
      if (isDup) {
        duplicateBadge = `<span class="badge badge-warning">Duplicate: ${escapeHtml(
          p.duplicate_info.match_type || 'Matched'
        )}</span>`;
      }

      let accessBadge = isAccessible
        ? '<span class="badge badge-success">PDF Accessible</span>'
        : '<span class="badge badge-danger">PDF Not Found / Paywalled</span>';

      card.innerHTML = `
        <div class="preview-card-top">
          <div style="display: flex; gap: 12px; align-items: flex-start;">
            <input type="checkbox" class="paper-select-box" data-id="${p.id}" ${
        selectedPaperIds.has(p.id) ? 'checked' : ''
      } style="margin-top: 5px; accent-color: var(--accent-primary); width: 16px; height: 16px; cursor: pointer;">
            <div>
              <div class="preview-title">${escapeHtml(p.title)}</div>
              <div class="preview-meta" style="margin-top: 6px;">
                <span><strong>Authors:</strong> ${escapeHtml(authorsStr)}</span>
                <span>&bull;</span>
                <span><strong>Year:</strong> ${escapeHtml(yearStr)}</span>
                <span>&bull;</span>
                <span><strong>Venue:</strong> ${escapeHtml(venueStr)}</span>
              </div>
            </div>
          </div>
          <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 6px;">
            ${accessBadge}
            ${duplicateBadge}
          </div>
        </div>

        ${p.abstract ? `<div class="preview-abstract">${escapeHtml(p.abstract)}</div>` : ''}

        <div class="preview-bottom">
          <div class="preview-tags">
            ${p.doi ? `<button class="btn btn-secondary btn-sm" onclick="copyToClipboard('${escapeHtml(p.doi)}', 'DOI copied')">DOI: ${escapeHtml(p.doi)}</button>` : ''}
            <span style="font-size: 11px; color: var(--text-dim);">Source: ${escapeHtml(p.metadata_source || 'Web')}</span>
          </div>
          <div class="preview-actions">
            <button class="btn btn-secondary btn-sm" onclick="openEditModal('${p.id}')">Edit</button>
            <button class="btn btn-danger btn-sm" onclick="removePreviewPaper('${p.id}')">Remove</button>
            ${p.original_url ? `<a href="${p.original_url}" target="_blank" rel="noopener" class="btn btn-secondary btn-sm">Original</a>` : ''}
          </div>
        </div>
      `;

      previewList.appendChild(card);
    });

    // Checkbox events
    document.querySelectorAll('.paper-select-box').forEach((cb) => {
      cb.addEventListener('change', (e) => {
        const id = e.target.getAttribute('data-id');
        if (e.target.checked) selectedPaperIds.add(id);
        else selectedPaperIds.delete(id);
      });
    });
  }

  // Start Downloads Button
  if (btnStartDownload) {
    btnStartDownload.addEventListener('click', async () => {
      const selectedIds = Array.from(selectedPaperIds);
      if (selectedIds.length === 0) {
        showToast('Please select at least one paper to download', 'warning');
        return;
      }

      window.currentBatchPaperIds = selectedIds;
      sessionStorage.setItem('currentBatchPaperIds', JSON.stringify(selectedIds));

      btnStartDownload.disabled = true;
      btnStartDownload.innerHTML = '<span class="status-dot"></span> Starting Batch...';

      try {
        const jobs = await API.createDownloadJobs(selectedIds, true);
        showToast(`Started download for ${jobs.length} papers!`, 'success');
        
        // Hide preview and show dashboard
        if (previewSection) previewSection.style.display = 'none';
        const downloadSection = document.getElementById('download-dashboard');
        if (downloadSection) {
          downloadSection.style.display = 'block';
          downloadSection.scrollIntoView({ behavior: 'smooth' });
        }
      } catch (err) {
        showToast(err.message, 'danger');
      } finally {
        btnStartDownload.disabled = false;
        btnStartDownload.innerHTML = 'Confirm &amp; Download Selected';
      }
    });
  }
});

function removePreviewPaper(paperId) {
  detectedPapers = detectedPapers.filter((p) => p.id !== paperId);
  selectedPaperIds.delete(paperId);
  const card = document.getElementById(`preview-${paperId}`);
  if (card) card.remove();
  showToast('Removed paper from batch', 'info');
}

// Edit Metadata Modal Handling
let currentEditingId = null;

function openEditModal(paperId) {
  const paper = detectedPapers.find((p) => p.id === paperId);
  if (!paper) return;

  currentEditingId = paperId;
  const modal = document.getElementById('edit-modal');
  if (!modal) return;

  document.getElementById('edit-title').value = paper.title || '';
  document.getElementById('edit-authors').value = (paper.authors || []).join(', ');
  document.getElementById('edit-year').value = paper.year || '';
  document.getElementById('edit-doi').value = paper.doi || '';
  document.getElementById('edit-venue').value = paper.journal_or_conference || '';
  document.getElementById('edit-pdf-url').value = paper.pdf_url || '';

  modal.classList.add('active');
}

function closeEditModal() {
  const modal = document.getElementById('edit-modal');
  if (modal) modal.classList.remove('active');
  currentEditingId = null;
}

async function saveMetadataEdits() {
  if (!currentEditingId) return;

  const title = document.getElementById('edit-title').value.trim();
  const authorsRaw = document.getElementById('edit-authors').value.trim();
  const authors = authorsRaw ? authorsRaw.split(',').map((a) => a.trim()) : [];
  const yearVal = parseInt(document.getElementById('edit-year').value, 10);
  const doi = document.getElementById('edit-doi').value.trim();
  const journal = document.getElementById('edit-venue').value.trim();
  const pdfUrl = document.getElementById('edit-pdf-url').value.trim();

  try {
    const updated = await API.updatePaper(currentEditingId, {
      title,
      authors,
      year: isNaN(yearVal) ? null : yearVal,
      doi: doi || null,
      journal_or_conference: journal || null,
      pdf_url: pdfUrl || null,
    });

    // Update in local array
    const idx = detectedPapers.findIndex((p) => p.id === currentEditingId);
    if (idx !== -1) {
      detectedPapers[idx] = { ...detectedPapers[idx], ...updated };
    }

    closeEditModal();
    showToast('Metadata updated successfully', 'success');
  } catch (err) {
    showToast('Failed to save edits: ' + err.message, 'danger');
  }
}
