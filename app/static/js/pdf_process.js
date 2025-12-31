// pdf_process.js

document.addEventListener('DOMContentLoaded', () => {
    // PDF Elements
    const pdfDropZone = document.getElementById('drop-zone-pdf');
    const pdfInput = document.getElementById('file-input-pdf');
    const pdfUploadContent = document.getElementById('upload-content-pdf');
    const pdfPreview = document.getElementById('file-preview-pdf');
    const pdfNameDisplay = document.getElementById('file-name-pdf');
    const btnRemovePdf = document.getElementById('btn-remove-pdf');

    // CSV Elements
    const csvDropZone = document.getElementById('drop-zone-csv-ref');
    const csvInput = document.getElementById('file-input-csv-ref');
    const csvUploadContent = document.getElementById('upload-content-csv');
    const csvPreview = document.getElementById('file-preview-csv');
    const csvNameDisplay = document.getElementById('file-name-csv');
    const btnRemoveCsv = document.getElementById('btn-remove-csv');

    // Logic
    const btnProcess = document.getElementById('btn-process-pdf');
    const form = document.getElementById('pdf-form');

    let pdfFile = null;
    let csvFile = null;

    function setupStagedUpload(config) {
        const { dropZone, input, uploadContent, preview, nameDisplay, btnRemove, isPdf } = config;

        dropZone.addEventListener('click', (e) => {
            if (e.target.closest('.btn-remove-file-absolute')) return;
            input.click();
        });

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                validateAndStage(e.dataTransfer.files[0]);
            }
        });

        input.addEventListener('change', (e) => {
            if (e.target.files.length) {
                validateAndStage(e.target.files[0]);
            }
        });

        btnRemove.addEventListener('click', (e) => {
            e.stopPropagation();
            resetStage();
        });

        function validateAndStage(file) {
            const ext = isPdf ? '.pdf' : '.csv';
            if (!file.name.toLowerCase().endsWith(ext)) {
                alert(`Error: Solo se permiten archivos ${ext}`);
                return;
            }

            // Set State
            if (isPdf) pdfFile = file;
            else csvFile = file;

            // Update UI
            uploadContent.classList.add('hidden');
            preview.classList.remove('hidden');
            nameDisplay.textContent = file.name;

            checkState();
        }

        function resetStage() {
            if (isPdf) pdfFile = null;
            else csvFile = null;
            input.value = '';

            uploadContent.classList.remove('hidden');
            preview.classList.add('hidden');
            nameDisplay.textContent = '';

            checkState();
        }
    }

    setupStagedUpload({
        dropZone: pdfDropZone, input: pdfInput, uploadContent: pdfUploadContent,
        preview: pdfPreview, nameDisplay: pdfNameDisplay, btnRemove: btnRemovePdf, isPdf: true
    });

    setupStagedUpload({
        dropZone: csvDropZone, input: csvInput, uploadContent: csvUploadContent,
        preview: csvPreview, nameDisplay: csvNameDisplay, btnRemove: btnRemoveCsv, isPdf: false
    });

    function checkState() {
        if (pdfFile && csvFile) {
            btnProcess.disabled = false;
        } else {
            btnProcess.disabled = true;
        }
    }

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (!pdfFile || !csvFile) return;

        const formData = new FormData();
        formData.append('pdf_file', pdfFile);
        formData.append('csv_file', csvFile);

        const originalText = btnProcess.innerHTML;
        btnProcess.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Procesando...';
        btnProcess.disabled = true;

        fetch('/api/process-pdf', {
            method: 'POST',
            body: formData
        })
            .then(res => {
                if (res.ok) return res.blob();
                return res.json().then(json => { throw new Error(json.error) });
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = "Etiquetas_Con_SKU.pdf";
                document.body.appendChild(a);
                a.click();
                a.remove();
            })
            .catch(err => {
                alert('Error: ' + err.message);
            })
            .finally(() => {
                btnProcess.innerHTML = originalText;
                btnProcess.disabled = false;
            });
    });
});
