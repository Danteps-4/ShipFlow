// excel_process.js

let currentData = [];

document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone-csv');
    const fileInput = document.getElementById('file-input-csv');
    const uploadStep = document.getElementById('upload-step');
    const processStep = document.getElementById('process-step');
    const tableBody = document.querySelector('#results-table tbody');
    const btnGenerate = document.getElementById('btn-generate');

    const uploadText = document.getElementById('upload-text');
    const filePreview = document.getElementById('file-preview');
    const fileNameDisplay = document.getElementById('file-name');
    const btnRemoveFile = document.getElementById('btn-remove-file');
    const btnProcessUpload = document.getElementById('btn-process-upload');
    const dropZoneIcon = dropZone.querySelector('i');

    // Modal Elements
    const modal = document.getElementById('exclusion-modal');
    const modalValidCount = document.getElementById('modal-valid-count');
    const modalExcludedCount = document.getElementById('modal-excluded-count');
    const excludedListContainer = document.getElementById('excluded-list-container');
    const excludedList = document.getElementById('excluded-list');
    const btnCloseModal = document.getElementById('btn-close-modal');

    // Close Modal Listener
    if (btnCloseModal) {
        btnCloseModal.addEventListener('click', () => {
            modal.classList.add('hidden');
        });
    }

    // Auto-load Batch if present in URL
    const params = new URLSearchParams(window.location.search);
    const batchId = params.get('batch_id');

    if (batchId) {
        // Switch to loading state
        uploadStep.innerHTML = '<div style="text-align:center; padding: 2rem; color: #666;"><i class="fas fa-spinner fa-spin fa-2x"></i><p style="margin-top:1rem; font-weight:600;">Cargando lote de pedidos...</p></div>';

        fetch(`/api/batch/${batchId}`)
            .then(res => res.json())
            .then(data => {
                if (data.error) throw new Error(data.error);

                // Success: Load Data
                currentData = data.records;
                renderSummary(data.summary);
                renderTable(data.records, data.meta);

                uploadStep.classList.add('hidden');
                processStep.classList.remove('hidden');

                // Clear URL param without reload
                window.history.replaceState({}, document.title, window.location.pathname);
            })
            .catch(err => {
                alert("Error cargando lote: " + err.message);
                // Reload to reset UI or show upload again
                window.location.href = "/excel";
            });
    }

    let stagedFile = null;

    // Drag & Drop
    dropZone.addEventListener('click', (e) => {
        // Prevent click if clicking remove or process
        if (e.target.closest('#btn-remove-file') || e.target.closest('#btn-process-upload')) return;
        fileInput.click();
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

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            validateAndStage(e.target.files[0]);
        }
    });

    btnRemoveFile.addEventListener('click', (e) => {
        e.stopPropagation(); // prevent triggering dropZone click
        resetUploadStage();
    });

    btnProcessUpload.addEventListener('click', (e) => {
        e.stopPropagation();
        if (stagedFile) {
            processFile(stagedFile);
        }
    });

    function validateAndStage(file) {
        // Extension Validation
        if (!file.name.toLowerCase().endsWith('.csv')) {
            alert("Error: Solo se permiten archivos .csv");
            resetUploadStage();
            return;
        }

        stagedFile = file;

        // Update UI
        uploadText.classList.add('hidden');
        dropZoneIcon.classList.add('hidden');
        filePreview.classList.remove('hidden');
        fileNameDisplay.textContent = file.name;
    }

    function resetUploadStage() {
        stagedFile = null;
        fileInput.value = ''; // clear input

        uploadText.classList.remove('hidden');
        dropZoneIcon.classList.remove('hidden');
        filePreview.classList.add('hidden');
        fileNameDisplay.textContent = '';
    }

    function processFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        // Show loading state? for now just process
        btnProcessUpload.textContent = 'Procesando...';
        btnProcessUpload.disabled = true;

        fetch('/api/parse-csv', {
            method: 'POST',
            body: formData
        })
            .then(res => res.json())
            .then(data => {
                btnProcessUpload.textContent = 'Procesar Archivo';
                btnProcessUpload.disabled = false;

                if (data.error) {
                    alert('Error: ' + data.error);
                    return;
                }
                // data structure: { records: [...], meta: { sucursales: [...], localidades: [...] } }
                currentData = data.records;
                renderSummary(data.summary);
                renderTable(data.records, data.meta);
                uploadStep.classList.add('hidden');
                processStep.classList.remove('hidden');
            })
            .catch(err => {
                alert('Error uploading file: ' + err);
                btnProcessUpload.textContent = 'Procesar Archivo';
                btnProcessUpload.disabled = false;
            });
    }

    function renderSummary(summary) {
        const container = document.getElementById('summary-stats');
        if (!summary) return;

        container.innerHTML = `
            <div class="stat-card">
                <div class="stat-value">${summary.domicilio}</div>
                <div class="stat-label">A Domicilio</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${summary.sucursal}</div>
                <div class="stat-label">A Sucursal</div>
            </div>
            <div class="stat-card ${summary.revisar > 0 ? 'warning' : ''}">
                <div class="stat-value">${summary.revisar}</div>
                <div class="stat-label">Para Revisar</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${summary.total}</div>
                <div class="stat-label">Total</div>
            </div>
        `;
    }

    function renderTable(data, meta) {
        tableBody.innerHTML = '';
        data.forEach((item, index) => {
            const tr = document.createElement('tr');

            // Status Logic
            const isMissing = item.status === 'MISSING';
            const statusClass = isMissing ? 'status-missing' : 'status-ok';
            const statusText = isMissing ? 'Revisar' : 'OK';

            // Match Value / Selection Logic
            let cellContent = '';
            if (isMissing) {
                // Determine options source
                let allOptions = [];
                let filteredOptions = [];
                let isSucursal = item.tipo_envio === 'SUCURSAL';

                if (isSucursal) {
                    allOptions = meta.sucursales || [];
                    // User requested ALL branches to be available
                    filteredOptions = allOptions;
                } else {
                    allOptions = meta.localidades || [];
                    // Filter Localities by Province
                    if (item.provincia_norm) {
                        filteredOptions = allOptions.filter(opt =>
                            opt.provincia && opt.provincia.includes(item.provincia_norm)
                        );
                        // Fallback
                        if (filteredOptions.length === 0) filteredOptions = allOptions;
                    } else {
                        filteredOptions = allOptions;
                    }
                }

                // Create Select for TomSelect
                // We use a unique ID for init
                const uniqueId = `select-${index}`;
                let selectHtml = `<select id="${uniqueId}" class="row-select tom-select-init" data-index="${index}" placeholder="Buscar...">`;

                // 1. Add Suggestions
                const suggestions = item.suggestions || [];
                if (suggestions.length > 0) {
                    selectHtml += `<optgroup label="Sugerencias recomendadas">`;
                    suggestions.forEach(sug => {
                        selectHtml += `<option value="${sug}" data-custom-properties="suggestion">⭐ ${sug}</option>`;
                    });
                    selectHtml += `</optgroup>`;
                    selectHtml += `<optgroup label="Todas las opciones">`;
                }

                const sugSet = new Set(suggestions);

                selectHtml += `<option value="">Buscar en ${filteredOptions.length} opciones...</option>`;

                filteredOptions.forEach(opt => {
                    const val = opt.value;
                    if (!sugSet.has(val)) {
                        selectHtml += `<option value="${val}">${val}</option>`;
                    }
                });

                if (suggestions.length > 0) {
                    selectHtml += `</optgroup>`;
                }

                selectHtml += `</select>`;

                // Add Manual/Deny Button
                selectHtml += `<button class="btn-deny" data-index="${index}" title="Cargar manualmente (Excluir del Excel)">
                    <i class="fas fa-times"></i> Manual
                </button>`;

                cellContent = `<div style="display:flex; align-items:center;">${selectHtml}</div>`;
            } else {
                cellContent = item.match_value || '<span style="color:red">No encontrado</span>';
            }

            tr.innerHTML = `
                <td>${item.nro_orden}</td>
                <td>${item.nombre} ${item.apellido}</td>
                <td>
                    ${item.calle} ${item.numero} <br>
                    <small class="text-muted">${item.raw_localidad}, ${item.raw_provincia} (${item.raw_cp})</small>
                </td>
                <td>${item.raw_ciudad || '-'}</td>
                <td>${item.tipo_envio}</td>
                <td>${cellContent}</td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
            `;

            // Re-render state if previously excluded (though currentData reloads on upload, this keeps local state if we eventually support re-render without reload)
            tr.dataset.index = index; // helper
            tableBody.appendChild(tr);
        });

        // Initialize TomSelect
        document.querySelectorAll('.tom-select-init').forEach(el => {
            new TomSelect(el, {
                create: false,
                sortField: {
                    field: "text",
                    direction: "asc"
                },
                maxOptions: null,
                dropdownParent: 'body'
            });
        });

        // Add Listeners for Deny Buttons
        document.querySelectorAll('.btn-deny').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = btn.dataset.index;
                // Find TR
                const tr = btn.closest('tr');
                const isExcluded = tr.classList.contains('row-excluded');

                if (isExcluded) {
                    // Re-include
                    tr.classList.remove('row-excluded');
                    btn.innerHTML = '<i class="fas fa-times"></i> Manual';
                    btn.style.backgroundColor = ''; // Reset
                    delete currentData[idx].manual_exclude; // Remove flag
                } else {
                    // Exclude
                    tr.classList.add('row-excluded');
                    btn.innerHTML = '<i class="fas fa-undo"></i> Incluir';
                    btn.style.backgroundColor = 'var(--text-muted)';
                    currentData[idx].manual_exclude = true; // Set flag
                }
            });
        });
    }

    // Modal Elements ... (unchanged)

    btnGenerate.addEventListener('click', () => {
        // Collect data
        const finalRecords = [];
        const excludedRecords = [];

        currentData.forEach((item, index) => {
            const select = document.querySelector(`.row-select[data-index="${index}"]`);
            let finalValue = item.match_value;
            if (select) finalValue = select.value;

            // Check Manual Exclusion flag
            if (item.manual_exclude) {
                excludedRecords.push(item);
                return; // Duplicate logic avoidance
            }

            // Standard Exclusion Logic (Missing & Empty)
            if (item.status === 'MISSING' && (!finalValue || finalValue.trim() === "")) {
                excludedRecords.push(item);
            } else {
                finalRecords.push({
                    ...item,
                    match_value: finalValue
                });
            }
        });

        if (finalRecords.length === 0) {
            alert("No hay pedidos válidos para generar.");
            return;
        }

        // Send ONLY valid records to backend
        fetch('/api/generate-excel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ records: finalRecords })
        })
            .then(res => {
                if (res.ok) return res.blob();
                throw new Error('Failed to generate excel');
            })
            .then(blob => {
                // Download file
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = "EnvioMasivoExcelPaquetes_cargado.xlsx";
                document.body.appendChild(a);
                a.click();
                a.remove();

                // Show Modal Summary
                modalValidCount.textContent = finalRecords.length;
                modalExcludedCount.textContent = excludedRecords.length;

                if (excludedRecords.length > 0) {
                    excludedListContainer.classList.remove('hidden');
                    excludedList.innerHTML = excludedRecords.map(r =>
                        `#${r.nro_orden} - ${r.nombre} ${r.apellido} <br> <span style="font-size:0.8em">${r.calle} ${r.numero}, ${r.raw_localidad}</span>`
                    ).join('<hr style="border-color:var(--border-color); margin: 5px 0;">');
                } else {
                    excludedListContainer.classList.add('hidden');
                    excludedList.innerHTML = '';
                }

                modal.classList.remove('hidden');
            })
            .catch(err => alert(err));
    });
});
