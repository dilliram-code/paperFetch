/**
 * PaperFetch V2 - Library & Download History Manager
 */

let currentQuery = '';
let currentYear = '';
let currentJournal = '';
let currentSort = 'created_at';
let currentOrder = 'desc';
let currentPage = 0;
const pageSize = 25;

async function loadLibrary() {
  const container = document.getElementById('library-table-body');
  const countEl = document.getElementById('library-total-count');
  if (!container) return;

  container.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 24px; color: var(--text-dim);">Loading library...</td></tr>';

  try {
    const params = {
      limit: pageSize,
      offset: currentPage * pageSize,
      sort_by: currentSort,
      order: currentOrder,
    };
    if (currentQuery) params.q = currentQuery;
    if (currentYear) params.year = currentYear;
    if (currentJournal) params.journal = currentJournal;

    const data = await API.getLibrary(params);
    const papers = data.items || [];
    if (countEl) countEl.textContent = `${data.total} paper(s)`;

    if (papers.length === 0) {
      container.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 32px; color: var(--text-dim);">No papers found matching criteria.</td></tr>';
      return;
    }

    container.innerHTML = '';
    papers.forEach((p) => {
      const tr = document.createElement('tr');
      const authors = (p.authors && p.authors.length > 0) ? p.authors.join(', ') : 'Unknown';
      const venue = p.journal_or_conference || p.publisher || '--';
      const fileSize = p.file_size_bytes ? formatBytes(p.file_size_bytes) : '--';

      tr.innerHTML = `
        <td class="paper-title-cell">
          <div style="font-weight: 600; color: #fff;">${escapeHtml(p.title)}</div>
          <div style="font-size: 11px; color: var(--text-dim); margin-top: 3px;">${escapeHtml(p.filename || '')}</div>
        </td>
        <td>${escapeHtml(authors)}</td>
        <td>${p.year || '--'}</td>
        <td>${escapeHtml(venue)}</td>
        <td>${fileSize}</td>
        <td>
          <div style="display: flex; gap: 6px; align-items: center;">
            ${p.local_path ? `<a href="/api/papers/${p.id}/download" download class="btn btn-secondary btn-sm">PDF</a>` : ''}
            <button class="btn btn-secondary btn-sm" onclick="copyPaperBibtex('${p.id}')">BibTeX</button>
            <button class="btn btn-danger btn-sm" onclick="confirmDeletePaper('${p.id}', '${escapeHtml(p.title)}')">Delete</button>
          </div>
        </td>
      `;
      container.appendChild(tr);
    });
  } catch (err) {
    container.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 24px; color: var(--accent-rose);">${escapeHtml(err.message)}</td></tr>`;
  }
}

async function copyPaperBibtex(paperId) {
  try {
    const bibtex = await API.getSingleBibtex(paperId);
    await copyToClipboard(bibtex, 'BibTeX citation copied!');
  } catch (err) {
    showToast('Failed to load BibTeX: ' + err.message, 'danger');
  }
}

let deleteTargetId = null;

function confirmDeletePaper(paperId, title) {
  deleteTargetId = paperId;
  const modal = document.getElementById('delete-modal');
  const titleSpan = document.getElementById('delete-paper-title');
  if (titleSpan) titleSpan.textContent = `"${title}"`;
  if (modal) modal.classList.add('active');
}

function closeDeleteModal() {
  const modal = document.getElementById('delete-modal');
  if (modal) modal.classList.remove('active');
  deleteTargetId = null;
}

async function executeDeletePaper() {
  if (!deleteTargetId) return;
  try {
    await API.deletePaper(deleteTargetId);
    showToast('Paper and file deleted from library', 'success');
    closeDeleteModal();
    loadLibrary();
  } catch (err) {
    showToast('Failed to delete paper: ' + err.message, 'danger');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.getElementById('library-search');
  if (searchInput) {
    let timeout = null;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        currentQuery = e.target.value.trim();
        currentPage = 0;
        loadLibrary();
      }, 300);
    });
  }

  const sortSelect = document.getElementById('library-sort');
  if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
      const [sortBy, order] = e.target.value.split(':');
      currentSort = sortBy;
      currentOrder = order;
      currentPage = 0;
      loadLibrary();
    });
  }

  loadLibrary();
});
