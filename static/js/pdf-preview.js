// PDF page preview strip with lightbox
// Usage:
//   const preview = new PdfPreviewStrip('containerId');
//   preview.load(serverFilename);
//   preview.clear();

class PdfPreviewStrip {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.pages = [];
        this.lightboxIndex = 0;
        this._buildLightbox();
    }

    _buildLightbox() {
        if (document.getElementById('_pdfLightbox')) return;
        const lb = document.createElement('div');
        lb.id = '_pdfLightbox';
        lb.className = 'page-lightbox';
        lb.innerHTML = `
            <button class="page-lightbox-close" id="_lbClose"><i class="fa-solid fa-xmark"></i></button>
            <button class="page-lightbox-nav prev" id="_lbPrev"><i class="fa-solid fa-chevron-left"></i></button>
            <img id="_lbImg" src="" alt="Page preview">
            <button class="page-lightbox-nav next" id="_lbNext"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="page-lightbox-counter" id="_lbCounter"></div>
        `;
        document.body.appendChild(lb);

        document.getElementById('_lbClose').addEventListener('click', () => this.closeLightbox());
        document.getElementById('_lbPrev').addEventListener('click',  () => this.lightboxNav(-1));
        document.getElementById('_lbNext').addEventListener('click',  () => this.lightboxNav(1));
        lb.addEventListener('click', e => { if (e.target === lb) this.closeLightbox(); });

        // keyboard nav
        document.addEventListener('keydown', e => {
            if (!lb.classList.contains('open')) return;
            if (e.key === 'Escape')      this.closeLightbox();
            if (e.key === 'ArrowLeft')   this.lightboxNav(-1);
            if (e.key === 'ArrowRight')  this.lightboxNav(1);
        });
    }

    openLightbox(index) {
        this.lightboxIndex = index;
        this._updateLightbox();
        document.getElementById('_pdfLightbox').classList.add('open');
    }

    closeLightbox() {
        document.getElementById('_pdfLightbox').classList.remove('open');
    }

    lightboxNav(dir) {
        this.lightboxIndex = (this.lightboxIndex + dir + this.pages.length) % this.pages.length;
        this._updateLightbox();
    }

    _updateLightbox() {
        document.getElementById('_lbImg').src = this.pages[this.lightboxIndex];
        document.getElementById('_lbCounter').textContent =
            `${this.lightboxIndex + 1} / ${this.pages.length}`;
        // hide nav arrows when there's only one page
        document.getElementById('_lbPrev').style.display = this.pages.length > 1 ? 'flex' : 'none';
        document.getElementById('_lbNext').style.display = this.pages.length > 1 ? 'flex' : 'none';
    }

    async load(filename) {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="pdf-preview-strip">
                <div class="pdf-preview-strip-header">
                    <h4><i class="fa-solid fa-file-pdf"></i> Document Preview</h4>
                </div>
                <div class="pdf-preview-loading">
                    <div class="mini-spinner"></div>
                    <span>Loading page previews...</span>
                </div>
            </div>`;

        try {
            const res  = await fetch(`/api/pdf-previews/${filename}`);
            const data = await res.json();

            if (data.error || !data.previews) {
                this.container.innerHTML = '';
                return;
            }

            this.pages = data.previews;
            this._render(data.page_count);
        } catch (e) {
            console.warn('PDF preview failed:', e);
            this.container.innerHTML = '';
        }
    }

    _render(pageCount) {
        const thumbsHtml = this.pages.map((src, i) => `
            <div class="pdf-page-thumb" data-index="${i}" title="Click to enlarge page ${i+1}">
                <img src="${src}" alt="Page ${i+1}" loading="lazy">
                <span class="thumb-label">Page ${i+1}</span>
            </div>`).join('');

        this.container.innerHTML = `
            <div class="pdf-preview-strip">
                <div class="pdf-preview-strip-header">
                    <h4><i class="fa-solid fa-file-pdf"></i> Document Preview</h4>
                    <span class="page-count-badge">${pageCount} page${pageCount !== 1 ? 's' : ''}</span>
                </div>
                <div class="pdf-preview-pages">${thumbsHtml}</div>
            </div>`;

        this.container.querySelectorAll('.pdf-page-thumb').forEach(el => {
            el.addEventListener('click', () => this.openLightbox(parseInt(el.dataset.index)));
        });
    }

    clear() {
        if (this.container) this.container.innerHTML = '';
        this.pages = [];
    }
}

window.PdfPreviewStrip = PdfPreviewStrip;
