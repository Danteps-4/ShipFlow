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

        try {
            const response = await fetch('/api/update-tracking', {
                method: 'POST',
                body: formData
            });

            loading.classList.add('hidden');
            btnProcess.disabled = false;

            if (!response.ok) {
                const err = await response.json();
                statsDiv.innerHTML = `<div class="stat-card error">Error: ${err.error || 'Unknown'}</div>`;
                return;
            }

            const data = await response.json();

            if (data.error) {
                statsDiv.innerHTML = `<div class="stat-card error">Error: ${data.error}</div>`;
                return;
            }

            renderResults(data.results || []);

        } catch (error) {
            console.error(error);
            loading.classList.add('hidden');
            btnProcess.disabled = false;
            statsDiv.innerHTML = `<div class="stat-card error">Error de red: ${error.message}</div>`;
        }
    });

    function renderResults(results) {
        let success = 0;
        let errors = 0;
        let skipped = 0;

        results.forEach(r => {
            if (r.status === 'SUCCESS') success++;
            else if (r.status === 'SKIPPED') skipped++;
            else errors++;

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

        statsDiv.innerHTML = `
            <div class="stat-card">
                <h3>${results.length}</h3>
                <p>Total Procesados</p>
            </div>
            <div class="stat-card success">
                <h3>${success}</h3>
                <p>Actualizados</p>
            </div>
             <div class="stat-card error">
                <h3>${errors}</h3>
                <p>Fallos</p>
            </div>
        `;
    }
});
