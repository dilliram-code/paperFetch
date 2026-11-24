/**
 * PaperFetch V2 - BibTeX Citation Studio
 */

let libraryPapers = [];
const selectedCitationIds = new Set();

async function loadCitationsStudio() {
  const paperListContainer = document.getElementById('citation-papers-list');
  const codeViewer = document.getElementById('bibtex-output');
  if (!paperListContainer) return;

  try {
    const data = await API.getLibrary({ limit: 100 });
    libraryPapers = data.items || [];

    if (libraryPapers.length === 0) {
      paperListContainer.innerHTML = '<div style="color: var(--text-dim); padding: 16px;">No papers available in library. Download some papers first!</div>';
      if (codeViewer) codeViewer.textContent = '% No citations available';
      return;
    }

    paperListContainer.innerHTML = '';
    // Select all by default
    libraryPapers.forEach((p) => selectedCitationIds.add(p.id));

    libraryPapers.forEach((p) => {
      const item = document.createElement('label');
      item.style.display = 'flex';
      item.style.alignItems = 'center';
      item.style.gap = '10px';
      item.style.padding = '8px 12px';
      item.style.borderRadius = '6px';
      item.style.cursor = 'pointer';
      item.style.border = '1px solid rgba(255, 255, 255, 0.05)';
      item.style.marginBottom = '6px';
      item.style.background = 'rgba(255, 255, 255, 0.02)';

      item.innerHTML = `
        <input type="checkbox" class="citation-cb" data-id="${p.id}" checked style="accent-color: var(--accent-primary);">
        <div style="flex: 1; font-size: 13px;">
          <div style="color: #fff; font-weight: 500;">${escapeHtml(p.title)}</div>
          <div style="color: var(--text-dim); font-size: 11px;">${p.first_author || 'Unknown'} (${p.year || 'n/a'})</div>
        </div>
      `;
      paperListContainer.appendChild(item);
    });

    document.querySelectorAll('.citation-cb').forEach((cb) => {
      cb.addEventListener('change', (e) => {
        const id = e.target.getAttribute('data-id');
        if (e.target.checked) selectedCitationIds.add(id);
        else selectedCitationIds.delete(id);
        updateBibtexOutput();
      });
    });

    updateBibtexOutput();
  } catch (err) {
    showToast('Failed to load citations: ' + err.message, 'danger');
  }
}

async function updateBibtexOutput() {
  const codeViewer = document.getElementById('bibtex-output');
  if (!codeViewer) return;

  const ids = Array.from(selectedCitationIds);
  if (ids.length === 0) {
    codeViewer.textContent = '% Select at least one paper on the left to view BibTeX citations';
    return;
  }

  codeViewer.textContent = '% Generating BibTeX citations...';
  try {
    const bibtex = await API.exportBibtex(ids);
    codeViewer.textContent = bibtex;
  } catch (err) {
    codeViewer.textContent = '% Failed to generate BibTeX: ' + err.message;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadCitationsStudio();

  const btnCopyBibtex = document.getElementById('btn-copy-bibtex');
  if (btnCopyBibtex) {
    btnCopyBibtex.addEventListener('click', () => {
      const codeViewer = document.getElementById('bibtex-output');
      if (codeViewer && codeViewer.textContent) {
        copyToClipboard(codeViewer.textContent, 'BibTeX copied to clipboard!');
      }
    });
  }

  const btnDownloadBib = document.getElementById('btn-download-bib');
  if (btnDownloadBib) {
    btnDownloadBib.addEventListener('click', () => {
      const codeViewer = document.getElementById('bibtex-output');
      if (!codeViewer || !codeViewer.textContent) return;

      const blob = new Blob([codeViewer.textContent], { type: 'application/x-bibtex;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'citations.bib';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('Downloaded citations.bib', 'success');
    });
  }

  const btnSelectAll = document.getElementById('btn-citation-select-all');
  if (btnSelectAll) {
    btnSelectAll.addEventListener('click', () => {
      document.querySelectorAll('.citation-cb').forEach((cb) => {
        cb.checked = true;
        selectedCitationIds.add(cb.getAttribute('data-id'));
      });
      updateBibtexOutput();
    });
  }
});
