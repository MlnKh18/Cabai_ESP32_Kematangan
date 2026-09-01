// =========================================================
// CABAI IOT DASHBOARD JAVASCRIPT LOGIC
// =========================================================

document.addEventListener('DOMContentLoaded', () => {
    
    // API Endpoints (relative path when served via HTTP/HTTPS, fallback for file://)
    const API_BASE = window.location.protocol.startsWith('http') ? '' : 'http://localhost:5001';

    // State Variables
    let autoMode = true;
    let pumpOverride = false;
    let moistureThreshold = 40;
    let telemetryChart = null;

    // DOM Elements
    const timeEl = document.getElementById('current-time');
    const valSoil = document.getElementById('val-soil');
    const valTemp = document.getElementById('val-temp');
    const valHumidity = document.getElementById('val-humidity');
    const valLight = document.getElementById('val-light');

    const barSoil = document.getElementById('bar-soil');
    const barTemp = document.getElementById('bar-temp');
    const barHumidity = document.getElementById('bar-humidity');
    const barLight = document.getElementById('bar-light');

    const toggleAutoMode = document.getElementById('toggle-auto-mode');
    const btnTogglePump = document.getElementById('btn-toggle-pump');
    const pumpBtnText = document.getElementById('pump-btn-text');
    const modeBadge = document.getElementById('mode-badge');
    const pumpBanner = document.getElementById('pump-status-banner');
    const pumpBannerTitle = document.getElementById('pump-banner-title');
    const pumpBannerSub = document.getElementById('pump-banner-sub');

    const inputThreshold = document.getElementById('input-threshold');
    const valThresholdDisplay = document.getElementById('val-threshold-display');
    const thresholdLabel = document.getElementById('threshold-label');

    const tableBody = document.getElementById('sensor-table-body');
    const btnRefresh = document.getElementById('btn-manual-refresh');
    const connectionBadge = document.getElementById('connection-badge');
    const esp32StatusText = document.getElementById('esp32-status-text');

    // ---------------------------------------------------------
    // 1. CLOCK UPDATE
    // ---------------------------------------------------------
    function updateClock() {
        const now = new Date();
        timeEl.textContent = now.toLocaleTimeString('id-ID');
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ---------------------------------------------------------
    // 2. CHART INITIALIZATION
    // ---------------------------------------------------------
    function initChart() {
        const ctx = document.getElementById('telemetryChart').getContext('2d');
        
        telemetryChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Suhu (°C)',
                        data: [],
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.05)',
                        borderWidth: 2,
                        pointRadius: 2,
                        tension: 0.3,
                        fill: true
                    },
                    {
                        label: 'Kelembapan Tanah (%)',
                        data: [],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.05)',
                        borderWidth: 2,
                        pointRadius: 2,
                        tension: 0.3,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(226, 232, 240, 0.8)' },
                        ticks: { color: '#64748b', font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' } }
                    },
                    y: {
                        grid: { color: 'rgba(226, 232, 240, 0.8)' },
                        ticks: { color: '#64748b', font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' } }
                    }
                }
            }
        });
    }
    initChart();

    // ---------------------------------------------------------
    // 3. FETCH & UPDATE LATEST DATA
    // ---------------------------------------------------------
    async function fetchLatestData() {
        try {
            const res = await fetch(`${API_BASE}/api/data/latest`);
            if (!res.ok) throw new Error('API Error');
            const json = await res.json();
            
            const sensor = json.sensor;
            const control = json.control;

            // Update UI Sensor values
            valSoil.textContent = Math.round(sensor.soil_moisture);
            valTemp.textContent = sensor.temperature.toFixed(1);
            valHumidity.textContent = Math.round(sensor.humidity);
            valLight.textContent = Math.round(sensor.light_intensity);

            // Progress Bars
            barSoil.style.width = `${Math.min(100, Math.max(0, sensor.soil_moisture))}%`;
            barTemp.style.width = `${Math.min(100, (sensor.temperature / 50) * 100)}%`;
            barHumidity.style.width = `${Math.min(100, Math.max(0, sensor.humidity))}%`;
            barLight.style.width = `${Math.min(100, (sensor.light_intensity / 1000) * 100)}%`;

            // Update Controls State from Server
            autoMode = control.auto_mode;
            pumpOverride = control.pump_override;
            moistureThreshold = control.moisture_threshold;

            toggleAutoMode.checked = autoMode;
            inputThreshold.value = moistureThreshold;
            valThresholdDisplay.textContent = `${moistureThreshold}%`;
            thresholdLabel.textContent = moistureThreshold;

            modeBadge.textContent = autoMode ? 'Mode Otomatis' : 'Mode Manual';

            // Pump Active status display
            const isPumpOn = sensor.pump_status || pumpOverride;
            if (isPumpOn) {
                btnTogglePump.classList.add('active');
                pumpBtnText.textContent = 'Matikan Pompa';
                pumpBanner.className = 'status-banner active';
                pumpBannerTitle.textContent = 'Pompa Sedang Menyiram 💧';
                pumpBannerSub.textContent = 'Irigasi tanaman cabai sedang aktif';
            } else {
                btnTogglePump.classList.remove('active');
                pumpBtnText.textContent = 'Nyalakan Pompa';
                pumpBanner.className = 'status-banner idle';
                pumpBannerTitle.textContent = 'Pompa Standby (Matikan)';
                pumpBannerSub.textContent = 'Menunggu instruksi otomatisasi / manual';
            }

            // Soil Status Category (Aligned with ESP32 RAW ADC calibration thresholds)
            const statusSoilDesc = document.getElementById('status-soil-desc');
            if (statusSoilDesc) {
                if (sensor.soil_moisture <= 36.6) {
                    statusSoilDesc.innerHTML = 'KERING ⚠️';
                    statusSoilDesc.style.color = '#ef4444';
                    statusSoilDesc.style.background = 'rgba(239, 68, 68, 0.1)';
                } else if (sensor.soil_moisture > 36.6 && sensor.soil_moisture < 83.0) {
                    statusSoilDesc.innerHTML = 'LEMBAP 👍';
                    statusSoilDesc.style.color = '#10b981';
                    statusSoilDesc.style.background = 'rgba(16, 185, 129, 0.1)';
                } else {
                    statusSoilDesc.innerHTML = 'BASAH 💧';
                    statusSoilDesc.style.color = '#3b82f6';
                    statusSoilDesc.style.background = 'rgba(59, 130, 246, 0.1)';
                }
            }

            // Status Online
            connectionBadge.classList.add('online');
            esp32StatusText.textContent = 'Terhubung';

        } catch (err) {
            connectionBadge.classList.remove('online');
            esp32StatusText.textContent = 'Terputus';
            console.warn('Backend server not connected or loading mock data:', err);
        }
    }

    // ---------------------------------------------------------
    // 4. FETCH HISTORY FOR CHART & TABLE
    // ---------------------------------------------------------
    async function fetchHistoryData() {
        try {
            const res = await fetch(`${API_BASE}/api/data/history?limit=15`);
            if (!res.ok) return;
            const json = await res.json();
            const history = json.history || [];

            if (history.length > 0) {
                const labels = history.map(item => item.timestamp);
                const temps = history.map(item => item.temperature);
                const soils = history.map(item => item.soil_moisture);

                // Update Chart
                telemetryChart.data.labels = labels;
                telemetryChart.data.datasets[0].data = temps;
                telemetryChart.data.datasets[1].data = soils;
                telemetryChart.update();

                // Update Table
                tableBody.innerHTML = '';
                history.reverse().forEach(row => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${row.timestamp}</td>
                        <td><strong>${row.soil_moisture}%</strong></td>
                        <td>${row.temperature}°C</td>
                        <td>${row.humidity}%</td>
                        <td>${row.light_intensity} Lux</td>
                        <td>
                            <span class="chip ${row.pump_status ? 'chip-success' : ''}">
                                ${row.pump_status ? 'Menyiram' : 'Matikan'}
                            </span>
                        </td>
                    `;
                    tableBody.appendChild(tr);
                });
            }
        } catch (e) {
            console.warn('Error fetching history:', e);
        }
    }

    // ---------------------------------------------------------
    // 5. CONTROL API ACTIONS
    // ---------------------------------------------------------
    async function sendControlUpdate(payload) {
        try {
            await fetch(`${API_BASE}/api/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            fetchLatestData();
        } catch (err) {
            alert('Gagal memperbarui kontrol: Server offline');
        }
    }

    // Toggle Auto Mode Event
    toggleAutoMode.addEventListener('change', (e) => {
        autoMode = e.target.checked;
        if (autoMode) {
            pumpOverride = false;
        }
        sendControlUpdate({ auto_mode: autoMode, pump_override: pumpOverride });
    });

    // Toggle Manual Pump Event
    btnTogglePump.addEventListener('click', () => {
        pumpOverride = !pumpOverride;
        if (pumpOverride) {
            autoMode = false;
            toggleAutoMode.checked = false;
        }
        sendControlUpdate({ pump_override: pumpOverride, auto_mode: autoMode });
    });

    // Change Threshold Slider Event
    inputThreshold.addEventListener('input', (e) => {
        valThresholdDisplay.textContent = `${e.target.value}%`;
        thresholdLabel.textContent = e.target.value;
    });

    inputThreshold.addEventListener('change', (e) => {
        sendControlUpdate({ moisture_threshold: parseFloat(e.target.value) });
    });

    // Refresh Button Event
    btnRefresh.addEventListener('click', () => {
        fetchLatestData();
        fetchHistoryData();
        updateLiveCameraFeed();
    });

    // ---------------------------------------------------------
    // 6. LIVE CAMERA STREAM & AI CAPTURE
    // ---------------------------------------------------------
    const camStream = document.getElementById('cam-stream');
    const btnCaptureAi = document.getElementById('btn-capture-ai');
    const aiClassName = document.getElementById('ai-class-name');
    const aiConfidence = document.getElementById('ai-confidence');
    const aiSnapshotTime = document.getElementById('ai-snapshot-time');
    const btnResetLive = document.getElementById('btn-reset-live');

    let currentStreamUrl = '';
    async function updateLiveCameraFeed() {
        if (!camStream) return;
        try {
            const res = await fetch(`${API_BASE}/camera/live`);
            if (res.ok) {
                const contentType = res.headers.get('content-type') || '';
                if (contentType.includes('application/json')) {
                    const data = await res.json();
                    if (data.stream_url && currentStreamUrl !== data.stream_url) {
                        currentStreamUrl = data.stream_url;
                        camStream.src = data.stream_url;
                    }
                } else if (!currentStreamUrl) {
                    camStream.src = `${API_BASE}/camera/live?t=${Date.now()}`;
                }
            }
        } catch (err) {
            if (!currentStreamUrl) {
                camStream.src = `${API_BASE}/camera/live?t=${Date.now()}`;
            }
        }
    }

    if (btnCaptureAi) {
        btnCaptureAi.addEventListener('click', async () => {
            try {
                btnCaptureAi.disabled = true;
                btnCaptureAi.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analisis AI...';

                let blob = null;
                // Tangkap frame live menggunakan Canvas HTML5 jika didukung browser
                if (camStream && camStream.complete && camStream.naturalWidth > 0) {
                    try {
                        const canvas = document.createElement('canvas');
                        canvas.width = camStream.naturalWidth || 640;
                        canvas.height = camStream.naturalHeight || 480;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(camStream, 0, 0, canvas.width, canvas.height);
                        blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.92));
                    } catch (e) {
                        console.warn('Canvas export tainted or CORS blocked, fallback to server capture:', e);
                        blob = null;
                    }
                }

                let res, data;
                if (blob && blob.size > 0) {
                    const formData = new FormData();
                    formData.append('file', blob, 'esp32_snapshot.jpg');
                    res = await fetch(`${API_BASE}/api/camera/test-upload`, {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    res = await fetch(`${API_BASE}/api/camera/capture`, { method: 'POST' });
                }

                data = await res.json();

                if (data.status === 'success') {
                    aiClassName.textContent = data.ai_result.class;
                    aiConfidence.textContent = data.ai_result.confidence;
                    aiSnapshotTime.textContent = data.timestamp;
                    if (btnResetLive) btnResetLive.style.display = 'flex';
                } else {
                    alert(`Gagal menganalisis foto: ${data.message || 'Error server'}`);
                }
            } catch (err) {
                console.error('Capture AI Error:', err);
                alert(`Gagal terhubung ke server (${err.message || 'Network error'}).`);
            } finally {
                btnCaptureAi.disabled = false;
                btnCaptureAi.innerHTML = '<i class="fa-solid fa-camera-retro"></i> <span>Ambil Foto ESP32-CAM</span>';
            }
        });
    }

    // Manual Image File Upload Event Listener
    const btnUploadTest = document.getElementById('btn-upload-test');
    const inputUploadFile = document.getElementById('input-upload-file');

    if (btnUploadTest && inputUploadFile) {
        btnUploadTest.addEventListener('click', () => {
            inputUploadFile.click();
        });

        inputUploadFile.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            try {
                btnUploadTest.disabled = true;
                btnUploadTest.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Uploading AI...';

                const formData = new FormData();
                formData.append('file', file);

                const res = await fetch(`${API_BASE}/api/camera/test-upload`, {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();

                if (data.status === 'success') {
                    if (camStream) {
                        camStream.src = `${API_BASE}${data.image_url}?t=${Date.now()}`;
                    }
                    aiClassName.textContent = data.ai_result.class;
                    aiConfidence.textContent = data.ai_result.confidence;
                    aiSnapshotTime.textContent = data.timestamp;
                    if (btnResetLive) btnResetLive.style.display = 'flex';
                } else {
                    alert(`Gagal mengupload foto: ${data.message}`);
                }
            } catch (err) {
                alert('Gagal mengunggah foto ke server.');
            } finally {
                btnUploadTest.disabled = false;
                btnUploadTest.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> <span>Upload Foto Uji Coba</span>';
                inputUploadFile.value = '';
            }
        });
    }

    // Reset Back to Live Stream Event Listener
    if (btnResetLive) {
        btnResetLive.addEventListener('click', async () => {
            try {
                btnResetLive.disabled = true;
                btnResetLive.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Resetting...';

                await fetch(`${API_BASE}/api/camera/reset-live`, { method: 'POST' });

                btnResetLive.style.display = 'none';
                currentStreamUrl = '';
                updateLiveCameraFeed();

                aiClassName.textContent = 'Belum Ada Analisis';
                aiConfidence.textContent = '0.00%';
                aiSnapshotTime.textContent = '-';
            } catch (err) {
                alert('Gagal mereset ke mode live.');
            } finally {
                btnResetLive.disabled = false;
                btnResetLive.innerHTML = '<i class="fa-solid fa-arrow-rotate-left"></i> <span>Hapus Foto & Kembali ke Live</span>';
            }
        });
    }

    // Sensor Polling Interval (every 1.5 seconds)
    fetchLatestData();
    fetchHistoryData();
    setInterval(() => {
        fetchLatestData();
        fetchHistoryData();
    }, 1500);

    // Fast Camera Stream Polling Interval (every 250ms for smooth live video)
    updateLiveCameraFeed();
    setInterval(updateLiveCameraFeed, 250);

});
