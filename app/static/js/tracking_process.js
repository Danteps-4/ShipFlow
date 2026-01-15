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

    // --- Backend Logic ---
    async function safeJson(response) {
        const text = await response.text();
        try {
            return text ? JSON.parse(text) : {};
        } catch (e) {
            console.error("JSON PARSE ERROR. Body:", text);
            throw new Error(`Respuesta inválida del servidor: ${text.substring(0, 100)}...`);
        }
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

        let globalStats = { success: 0, errors: 0, processed_count: 0, total: 0 };

        try {
            // Step 1: Upload
            const responseUpload = await fetch('/api/tracking/upload', {
                method: 'POST',
                body: formData
            });

            if (!responseUpload.ok) {
                const errData = await safeJson(responseUpload);
                throw new Error(errData.error || `Upload failed with status ${responseUpload.status}`);
            }

            const uploadData = await safeJson(responseUpload);
            const batchId = uploadData.batch_id;
            const totalExpected = uploadData.total;
            globalStats.total = totalExpected;
            updateStatsDisplay(globalStats);

            // Step 2: Batch Loop
            let completed = false;

            while (!completed) {
                // Request next chunk
                const resBatch = await fetch(`/api/tracking/batch/${batchId}?limit=5`, {
                    method: 'POST'
                });

                if (!resBatch.ok) {
                    const errData = await safeJson(resBatch);
                    throw new Error(errData.detail || errData.error || `Batch error status ${resBatch.status}`);
                }

                const batchData = await safeJson(resBatch);

                // Update Stats based on response
                // Response Format: { sent, failed, remaining, items: [...] }
                const items = batchData.items || [];

                if (items.length > 0) {
                    appendResults(items, globalStats);
                }

                // Check termination condition
                // If remaining is 0, we assume done. Or checking if we received items.
                // Or simply checking if remaining is 0.
                if (batchData.remaining === 0) {
                    completed = true;
                }

                // Safety break if we get 0 items but remaining > 0 (stuck)
                if (items.length === 0 && batchData.remaining > 0) {
                    console.warn("Stuck batch? 0 items returned but remaining > 0");
                    // Optional wait or break
                    await new Promise(r => setTimeout(r, 2000));
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

    function appendResults(items, stats) {
        items.forEach(r => {
            if (r.ok) {
                stats.success++;
            } else {
                stats.errors++;
            }
            stats.processed_count++;

            const row = document.createElement('tr');

            let statusBadge = '';
            if (r.ok) statusBadge = '<span class="badge success">OK</span>';
            else statusBadge = '<span class="badge error">ERROR</span>';

            const reason = r.error || r.reason || '';

            row.innerHTML = `
                <td>${r.order_id || r.order}</td>
                <td>${statusBadge}</td>
                <td>${reason}</td>
            `;
            resultsTable.appendChild(row);
        });

        updateStatsDisplay(stats);
    }

    function updateStatsDisplay(stats) {
        // Safe division
        let progress = 0;
        if (stats.total > 0) {
            progress = Math.round((stats.processed_count / stats.total) * 100);
        }

        statsDiv.innerHTML = `
            <div class="stat-card">
                <h3>${stats.processed_count} / ${stats.total} (${progress}%)</h3>
                <p>Procesados</p>
            </div>
            <div class="stat-card success">
                <h3>${stats.success}</h3>
                <p>Enviados</p>
            </div>
             <div class="stat-card error">
                <h3>${stats.errors}</h3>
                <p>Fallos</p>
            </div>
        `;
    }
});
