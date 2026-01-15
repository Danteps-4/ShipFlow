document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone-track');
    const fileInput = document.getElementById('file-input-track');
    const filePreview = document.getElementById('file-preview');
    const fileNameDisplay = document.getElementById('file-name');
    const uploadText = document.getElementById('upload-text');
    const btnProcess = document.getElementById('btn-process-upload');
    const resultsArea = document.getElementById('results-area');
    const loading = document.getElementById('loading');
    const resultsTable = document.getElementById('results-table').querySelector('tbody');
    const statsDiv = document.getElementById('stats');

    let selectedFile = null;

    // --- Drag & Drop ---
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--primary-color)';
        dropZone.style.backgroundColor = 'rgba(52, 152, 219, 0.05)';
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#ccc';
        dropZone.style.backgroundColor = 'transparent';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#ccc';
        dropZone.style.backgroundColor = 'transparent';
        if (e.dataTransfer.files.length) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    dropZone.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileSelect(e.target.files[0]);
        }
    });

    function handleFileSelect(file) {
        selectedFile = file;
        fileNameDisplay.textContent = file.name;
        uploadText.classList.add('hidden');
        filePreview.classList.remove('hidden');
    }

    // --- Processing ---
    btnProcess.addEventListener('click', async (e) => {
        e.stopPropagation(); // Prevent dropZone click
        if (!selectedFile) return;

        resultsArea.classList.remove('hidden');
        loading.classList.remove('hidden');
        resultsTable.innerHTML = '';
        statsDiv.innerHTML = '';
        btnProcess.disabled = true;

        const formData = new FormData();
        formData.append('file', selectedFile);

        let globalStats = { success: 0, errors: 0, skipped: 0, total: 0, processed_count: 0 };

        try {
            // Step 1: Upload
            const responseUpload = await fetch('/api/tracking/upload', {
                method: 'POST',
                body: formData
            });

            if (!responseUpload.ok) {
                const text = await responseUpload.text();
                let errMsg = text;
                try {
                    const json = JSON.parse(text);
                    errMsg = json.error || text;
                } catch (e) { }
                throw new Error(`Upload Failed: ${errMsg}`);
            }

            const uploadData = await responseUpload.json();
            const batchId = uploadData.batch_id;
            const totalExpected = uploadData.total;
            globalStats.total = totalExpected;
            updateStatsDisplay(globalStats);

            // Step 2: Batch Loop
            let completed = false;

            while (!completed) {
                const resBatch = await fetch(`/api/tracking/batch/${batchId}?limit=10`, {
                    method: 'POST'
                });

                if (!resBatch.ok) {
                    // Try to read error
                    const text = await resBatch.text();
                    console.error("Batch Error:", text);
                    // We can try to continue or abort? Abort for now
                    throw new Error(`Batch Processing Failed: ${text}`);
                }

                let batchData;
                try {
                    batchData = await resBatch.json();
                } catch (e) {
                    throw new Error("Invalid JSON from server (possible timeout/crash)");
                }

                if (batchData.results && batchData.results.length > 0) {
                    appendResults(batchData.results, globalStats);
                }

                if (batchData.completed) {
                    completed = true;
                }
            }

            loading.classList.add('hidden');
            btnProcess.disabled = false;

        } catch (error) {
            console.error(error);
            loading.classList.add('hidden');
            btnProcess.disabled = false;
            statsDiv.innerHTML += `<div class="stat-card error" style="width:100%">Error crítico: ${error.message}</div>`;
        }
    });

    function appendResults(results, stats) {
        results.forEach(r => {
            if (r.status === 'SUCCESS') stats.success++;
            else if (r.status === 'SKIPPED') stats.skipped++;
            else stats.errors++;

            stats.processed_count++;

            const row = document.createElement('tr');

            let statusBadge = '';
            if (r.status === 'SUCCESS') statusBadge = '<span class="badge success">OK</span>';
            else if (r.status === 'SKIPPED') statusBadge = '<span class="badge warning">OMITIDO</span>';
            else statusBadge = '<span class="badge error">ERROR</span>';

            row.innerHTML = `
                <td>${r.order}</td>
                <td>${statusBadge}</td>
                <td>${r.reason || r.details || ''}</td>
            `;
            resultsTable.appendChild(row);
        });

        updateStatsDisplay(stats);
    }

    function updateStatsDisplay(stats) {
        statsDiv.innerHTML = `
            <div class="stat-card">
                <h3>${stats.processed_count} / ${stats.total}</h3>
                <p>Procesados</p>
            </div>
            <div class="stat-card success">
                <h3>${stats.success}</h3>
                <p>Actualizados</p>
            </div>
             <div class="stat-card error">
                <h3>${stats.errors}</h3>
                <p>Fallos</p>
            </div>
        `;
    }
});
