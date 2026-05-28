// PDF preview system — shows before/after pages for each tool

class PDFPreview {
    constructor(containerId, toolName) {
        this.container = document.getElementById(containerId);
        this.toolName = toolName;
        this.currentFilename = null;
        this.previewData = null;
        this.originalData = null;
        this.init();
    }

    init() {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="preview-section" id="previewSection" style="display: none;">
                <div class="preview-header">
                    <h3><i class="fa-solid fa-eye"></i> Full PDF Preview</h3>
                    <div class="preview-actions">
                        <button class="btn btn-outline btn-sm" onclick="this.refreshPreview()">
                            <i class="fa-solid fa-refresh"></i> Refresh
                        </button>
                        <button class="btn btn-primary btn-sm" onclick="this.downloadResult()">
                            <i class="fa-solid fa-download"></i> Download
                        </button>
                    </div>
                </div>
                <div class="preview-content">
                    <div class="preview-loading" id="previewLoading">
                        <div class="loading-spinner"></div>
                        <p>Generating full PDF preview...</p>
                    </div>
                    <div class="preview-result" id="previewResult" style="display: none;">
                        <div class="preview-comparison-full">
                            <div class="preview-column">
                                <h4><i class="fa-solid fa-file-pdf"></i> Original PDF</h4>
                                <div class="preview-pages-container" id="originalPages"></div>
                            </div>
                            <div class="preview-arrow-vertical">
                                <i class="fa-solid fa-arrow-down"></i>
                                <span>Preview Result</span>
                            </div>
                            <div class="preview-column">
                                <h4><i class="fa-solid fa-file-pdf"></i> Result PDF</h4>
                                <div class="preview-pages-container" id="resultPages"></div>
                            </div>
                        </div>
                    </div>
                    <div class="preview-error" id="previewError" style="display: none;">
                        <i class="fa-solid fa-exclamation-triangle"></i>
                        <p>Failed to generate preview</p>
                    </div>
                </div>
            </div>
        `;
    }

    async generatePreview(filename, params = {}) {
        this.currentFilename = filename;
        const previewSection = document.getElementById('previewSection');
        const previewLoading = document.getElementById('previewLoading');
        const previewResult  = document.getElementById('previewResult');
        const previewError   = document.getElementById('previewError');

        previewSection.style.display = 'block';
        previewLoading.style.display = 'block';
        previewResult.style.display  = 'none';
        previewError.style.display   = 'none';

        try {
            // load original pages
            const originalResponse = await fetch(`/api/preview-original/${filename}`);
            if (originalResponse.ok) {
                this.originalData = await originalResponse.json();
                this.renderPages('originalPages', this.originalData.original_images, 'Original');
            }

            // load processed result
            const queryParams   = new URLSearchParams(params).toString();
            const previewResponse = await fetch(`/api/preview/${this.toolName}/${filename}?${queryParams}`);
            const previewData   = await previewResponse.json();

            if (previewData.error) {
                throw new Error(previewData.error);
            }

            this.previewData = previewData;
            this.renderPages('resultPages', previewData.preview_images, 'Result');

            previewLoading.style.display = 'none';
            previewResult.style.display  = 'block';

        } catch (error) {
            console.error('Preview generation failed:', error);
            previewLoading.style.display = 'none';
            previewError.style.display   = 'block';
        }
    }

    renderPages(containerId, imageUrls, label) {
        const container = document.getElementById(containerId);
        if (!container || !imageUrls) return;

        container.innerHTML = '';

        const pageInfo = document.createElement('div');
        pageInfo.className = 'page-count-info';
        pageInfo.innerHTML = `<small>${imageUrls.length} page${imageUrls.length !== 1 ? 's' : ''}</small>`;
        container.appendChild(pageInfo);

        const pagesGrid = document.createElement('div');
        pagesGrid.className = 'preview-pages-grid';

        imageUrls.forEach((imageUrl, index) => {
            const pageItem = document.createElement('div');
            pageItem.className = 'preview-page-item';

            const img = document.createElement('img');
            img.src     = imageUrl;
            img.alt     = `${label} Page ${index + 1}`;
            img.loading = 'lazy';

            const pageNumber = document.createElement('div');
            pageNumber.className   = 'preview-page-number';
            pageNumber.textContent = index + 1;

            pageItem.appendChild(img);
            pageItem.appendChild(pageNumber);
            pagesGrid.appendChild(pageItem);
        });

        container.appendChild(pagesGrid);
    }

    refreshPreview() {
        if (this.currentFilename) {
            const params = this.getFormParameters();
            this.generatePreview(this.currentFilename, params);
        }
    }

    downloadResult() {
        if (this.previewData && this.previewData.preview_pdf) {
            window.location.href = this.previewData.preview_pdf;
        }
    }

    // override in subclasses to pass tool-specific form values
    getFormParameters() {
        return {};
    }

    hide() {
        const previewSection = document.getElementById('previewSection');
        if (previewSection) {
            previewSection.style.display = 'none';
        }
    }
}

class WatermarkPreview extends PDFPreview {
    getFormParameters() {
        const textInput = document.querySelector('input[name="text"]');
        return { text: textInput ? textInput.value : 'SAMPLE' };
    }
}

class RotatePreview extends PDFPreview {
    getFormParameters() {
        const angleInput = document.querySelector('input[name="angle"]');
        return { angle: angleInput ? angleInput.value : '90' };
    }
}

class RemovePagesPreview extends PDFPreview {
    getFormParameters() {
        const pagesInput = document.querySelector('input[name="pages"]');
        return { pages: pagesInput ? pagesInput.value : '1' };
    }
}

class ProtectPreview extends PDFPreview {
    getFormParameters() {
        const passwordInput = document.querySelector('input[name="password"]');
        return { password: passwordInput ? passwordInput.value : 'preview123' };
    }
}

class MergePreview extends PDFPreview {
    constructor(containerId, toolName) {
        super(containerId, toolName);
        this.uploadedFiles = [];
    }

    addFile(filename) {
        if (!this.uploadedFiles.includes(filename)) {
            this.uploadedFiles.push(filename);
        }
    }

    getFormParameters() {
        return { files: this.uploadedFiles.join(',') };
    }

    async generateMergePreview() {
        if (this.uploadedFiles.length < 2) {
            alert('Please upload at least 2 files to preview merge');
            return;
        }
        const params = this.getFormParameters();
        await this.generatePreview(this.uploadedFiles[0], params);
    }
}

window.PDFPreview        = PDFPreview;
window.WatermarkPreview  = WatermarkPreview;
window.RotatePreview     = RotatePreview;
window.RemovePagesPreview = RemovePagesPreview;
window.ProtectPreview    = ProtectPreview;
window.MergePreview      = MergePreview;
