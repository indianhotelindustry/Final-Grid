/**
 * checkin-camera.js — Camera selection, switching, and photo capture for check-in.
 *
 * CSP-safe: served from /static/js/ ('self'). No inline nonce required.
 * Loaded after Bootstrap JS via {% block scripts %} in checkin_new.html.
 *
 * Features:
 *  - Enumerate all video input devices and populate a dropdown
 *  - Save / restore camera preference via localStorage
 *  - Switch camera without page reload (stops old stream, starts new)
 *  - "Switch" button cycles through cameras (touch-friendly)
 *  - Capture, Retake, Stop controls
 *  - Clear permission/error messages in UI (no alert() dialogs)
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'pms_preferred_camera_id';

    // ── DOM refs ─────────────────────────────────────────────────────────────
    var videoEl      = document.getElementById('webcam');
    var canvasEl     = document.getElementById('photoCanvas');
    var previewImg   = document.getElementById('webcamPreview');
    var cameraSelect = document.getElementById('cameraSelect');
    var refreshBtn   = document.getElementById('refreshCameras');
    var switchBtn    = document.getElementById('switchCamera');
    var startBtn     = document.getElementById('startWebcam');
    var captureBtn   = document.getElementById('capturePhoto');
    var retakeBtn    = document.getElementById('retakePhoto');
    var stopBtn      = document.getElementById('stopWebcam');
    var msgEl        = document.getElementById('cameraMessage');
    var photoDataInput = document.getElementById('webcamPhotoData');

    // Bail out silently if this page doesn't have the webcam section
    if (!startBtn) return;

    // ── State ─────────────────────────────────────────────────────────────────
    var activeStream = null;
    var deviceList   = [];   // Array of MediaDeviceInfo

    // ── Preference helpers ───────────────────────────────────────────────────
    function savePreference(deviceId) {
        try { localStorage.setItem(STORAGE_KEY, deviceId || ''); } catch (_) {}
    }

    function loadPreference() {
        try { return localStorage.getItem(STORAGE_KEY) || ''; } catch (_) { return ''; }
    }

    // ── Status message ───────────────────────────────────────────────────────
    function showMsg(text, isError) {
        if (!msgEl) return;
        msgEl.textContent   = text;
        msgEl.className     = 'small mb-1 ' + (isError ? 'text-danger' : 'text-success');
        msgEl.style.display = text ? '' : 'none';
    }

    // ── Stop active stream tracks ────────────────────────────────────────────
    function stopStream() {
        if (activeStream) {
            activeStream.getTracks().forEach(function (t) { t.stop(); });
            activeStream = null;
        }
        if (videoEl) {
            videoEl.srcObject = null;
            videoEl.style.display = 'none';
        }
    }

    // ── Enumerate cameras ────────────────────────────────────────────────────
    async function enumerateCameras() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
            showMsg('Camera API not supported in this browser.', true);
            return [];
        }
        try {
            var devices = await navigator.mediaDevices.enumerateDevices();
            return devices.filter(function (d) { return d.kind === 'videoinput'; });
        } catch (err) {
            showMsg('Could not list cameras: ' + err.message, true);
            return [];
        }
    }

    // ── Populate dropdown ────────────────────────────────────────────────────
    async function populateCameraSelect(preferDeviceId) {
        var cameras = await enumerateCameras();
        deviceList  = cameras;

        if (!cameraSelect) return;

        cameraSelect.innerHTML = '';

        if (cameras.length === 0) {
            var opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'No camera detected';
            cameraSelect.appendChild(opt);
            showMsg('No camera detected.', true);
            if (switchBtn) switchBtn.classList.add('d-none');
            return;
        }

        // Determine which device to pre-select
        var preferred = preferDeviceId !== undefined
            ? preferDeviceId
            : (loadPreference() || cameras[0].deviceId);

        cameras.forEach(function (cam, idx) {
            var opt = document.createElement('option');
            opt.value = cam.deviceId;
            // Labels are empty strings before permission is granted
            opt.textContent = cam.label || ('Camera ' + (idx + 1));
            cameraSelect.appendChild(opt);
        });

        // Select the preferred camera (fall back to first if not found)
        var found = cameras.some(function (c) { return c.deviceId === preferred; });
        cameraSelect.value = found ? preferred : cameras[0].deviceId;

        // Show Switch button only when multiple cameras exist
        if (switchBtn) {
            switchBtn.classList.toggle('d-none', cameras.length < 2);
        }

        showMsg('', false);
    }

    // ── Start stream for a specific deviceId ─────────────────────────────────
    async function startCamera(deviceId) {
        stopStream();
        showMsg('', false);

        var constraints = {
            video: deviceId
                ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
                : { width: { ideal: 1280 }, height: { ideal: 720 } }
        };

        try {
            activeStream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch (err) {
            // Exact device unavailable — try without constraint
            if (deviceId && (err.name === 'OverconstrainedError' || err.name === 'NotFoundError')) {
                showMsg('Selected camera unavailable. Switching to default camera.', true);
                try {
                    activeStream = await navigator.mediaDevices.getUserMedia({ video: true });
                    // Re-populate so the dropdown reflects actual device
                    var fallbackId = activeStream.getVideoTracks()[0].getSettings().deviceId;
                    await populateCameraSelect(fallbackId);
                    if (cameraSelect) cameraSelect.value = fallbackId || '';
                } catch (fallbackErr) {
                    showMsg('Camera access denied. Please allow camera permission in your browser.', true);
                    return false;
                }
            } else if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                showMsg('Camera access denied. Please allow camera permission in your browser.', true);
                return false;
            } else {
                showMsg('Camera not available: ' + err.message, true);
                return false;
            }
        }

        // After permission is granted, device labels become available — refresh labels
        // (only if labels were placeholder text before)
        var firstOpt = cameraSelect && cameraSelect.options[0];
        if (firstOpt && /^Camera \d+$/.test(firstOpt.textContent)) {
            var runningId = activeStream.getVideoTracks()[0].getSettings().deviceId;
            await populateCameraSelect(runningId || deviceId);
        }

        videoEl.srcObject = activeStream;
        videoEl.style.display = '';
        videoEl.play().catch(function () {});
        return true;
    }

    // ── UI state ─────────────────────────────────────────────────────────────
    function setLiveUI() {
        if (startBtn)   startBtn.style.display   = 'none';
        if (captureBtn) captureBtn.style.display  = '';
        if (retakeBtn)  retakeBtn.style.display   = 'none';
        if (stopBtn)    stopBtn.style.display     = '';
        if (previewImg) previewImg.style.display  = 'none';
    }

    function setIdleUI() {
        if (startBtn)   startBtn.style.display   = '';
        if (captureBtn) captureBtn.style.display  = 'none';
        if (retakeBtn)  retakeBtn.style.display   = 'none';
        if (stopBtn)    stopBtn.style.display     = 'none';
    }

    function setPostCaptureUI() {
        if (startBtn)   startBtn.style.display   = 'none';
        if (captureBtn) captureBtn.style.display  = 'none';
        if (retakeBtn)  retakeBtn.style.display   = '';
        if (stopBtn)    stopBtn.style.display     = 'none';
    }

    // ── Capture ──────────────────────────────────────────────────────────────
    function doCapture() {
        if (!videoEl || !canvasEl) return;
        canvasEl.width  = videoEl.videoWidth  || 640;
        canvasEl.height = videoEl.videoHeight || 480;
        canvasEl.getContext('2d').drawImage(videoEl, 0, 0);
        var dataUrl = canvasEl.toDataURL('image/jpeg', 0.85);
        if (photoDataInput) photoDataInput.value = dataUrl;
        if (previewImg) {
            previewImg.src = dataUrl;
            previewImg.style.display = '';
        }
        stopStream();
        setPostCaptureUI();
        showMsg('Photo captured.', false);
    }

    // ── Events ───────────────────────────────────────────────────────────────

    // Start Camera
    startBtn.addEventListener('click', async function () {
        // If no enumeration yet, populate first (may show placeholder names
        // until permission is granted — startCamera will refresh them)
        if (deviceList.length === 0) {
            await populateCameraSelect();
        }
        var deviceId = cameraSelect ? cameraSelect.value : '';
        var ok = await startCamera(deviceId);
        if (ok) {
            if (deviceId) savePreference(deviceId);
            setLiveUI();
        }
    });

    // Capture Photo
    if (captureBtn) {
        captureBtn.addEventListener('click', function () {
            doCapture();
        });
    }

    // Retake — restart stream with same selected camera
    if (retakeBtn) {
        retakeBtn.addEventListener('click', async function () {
            if (previewImg) previewImg.style.display = 'none';
            if (photoDataInput) photoDataInput.value = '';
            var deviceId = cameraSelect ? cameraSelect.value : '';
            var ok = await startCamera(deviceId);
            if (ok) setLiveUI();
        });
    }

    // Stop
    if (stopBtn) {
        stopBtn.addEventListener('click', function () {
            stopStream();
            setIdleUI();
            showMsg('', false);
        });
    }

    // Camera selector change — switch live if stream is active
    if (cameraSelect) {
        cameraSelect.addEventListener('change', async function () {
            var newId = this.value;
            if (!newId) return;
            savePreference(newId);
            if (activeStream) {
                var ok = await startCamera(newId);
                if (ok) setLiveUI();
            }
        });
    }

    // Refresh Cameras button
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async function () {
            // Request temporary permission so labels become available
            if (!activeStream) {
                try {
                    var tmp = await navigator.mediaDevices.getUserMedia({ video: true });
                    tmp.getTracks().forEach(function (t) { t.stop(); });
                } catch (err) {
                    showMsg('Camera access denied. Please allow camera permission in your browser.', true);
                    return;
                }
            }
            var currentId = cameraSelect ? cameraSelect.value : '';
            await populateCameraSelect(currentId);
            showMsg('Camera list refreshed.', false);
            setTimeout(function () { showMsg('', false); }, 2500);
        });
    }

    // Switch Camera — cycle to next device
    if (switchBtn) {
        switchBtn.addEventListener('click', async function () {
            if (deviceList.length < 2) return;
            var currentId  = cameraSelect ? cameraSelect.value : '';
            var currentIdx = deviceList.findIndex(function (d) { return d.deviceId === currentId; });
            var nextIdx    = (currentIdx + 1) % deviceList.length;
            var nextId     = deviceList[nextIdx].deviceId;
            if (cameraSelect) cameraSelect.value = nextId;
            savePreference(nextId);
            var ok = await startCamera(nextId);
            if (ok) setLiveUI();
        });
    }

    // ── Init: enumerate cameras on load (no permission prompt yet) ───────────
    function init() {
        populateCameraSelect();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

}());
