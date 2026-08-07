/**
 * Voice-Activated Front Desk Assistant
 *
 * Uses the Web Speech API (built into Chrome/Edge) for speech recognition
 * and speech synthesis for responses. Falls back gracefully on unsupported browsers.
 *
 * Activated by clicking the mic button or pressing Ctrl+Shift+V.
 */
(function () {
    'use strict';

    // ── Feature detection ───────────────────────────────────────────────
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        // Browser doesn't support speech recognition — hide the UI
        var btn = document.getElementById('voiceAssistantBtn');
        if (btn) btn.style.display = 'none';
        return;
    }

    // ── State ───────────────────────────────────────────────────────────
    var recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-IN';  // Indian English
    recognition.maxAlternatives = 1;

    var isListening = false;
    var micBtn = document.getElementById('voiceAssistantBtn');
    var overlay = document.getElementById('voiceOverlay');
    var overlayStatus = document.getElementById('voiceStatus');
    var overlayTranscript = document.getElementById('voiceTranscript');
    var overlayResponse = document.getElementById('voiceResponse');

    if (!micBtn || !overlay) return;

    // ── Create overlay if not in DOM ────────────────────────────────────
    function showOverlay() {
        overlay.classList.add('active');
        overlayTranscript.textContent = '';
        overlayResponse.textContent = '';
        overlayStatus.textContent = 'Listening...';
        overlayStatus.className = 'voice-status listening';
    }

    function hideOverlay() {
        overlay.classList.remove('active');
    }

    function setStatus(text, cls) {
        if (overlayStatus) {
            overlayStatus.textContent = text;
            overlayStatus.className = 'voice-status ' + (cls || '');
        }
    }

    // ── Speech synthesis ────────────────────────────────────────────────
    function speak(text) {
        if (!window.speechSynthesis || !text) return;
        window.speechSynthesis.cancel();
        var utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'en-IN';
        utterance.rate = 1.05;
        utterance.pitch = 1.0;
        // Try to use a female voice if available
        var voices = window.speechSynthesis.getVoices();
        for (var i = 0; i < voices.length; i++) {
            if (voices[i].lang.startsWith('en') && voices[i].name.toLowerCase().indexOf('female') >= 0) {
                utterance.voice = voices[i];
                break;
            }
        }
        window.speechSynthesis.speak(utterance);
    }

    // ── Recognition events ──────────────────────────────────────────────
    recognition.onstart = function () {
        isListening = true;
        micBtn.classList.add('listening');
        showOverlay();
    };

    recognition.onresult = function (event) {
        var transcript = '';
        var isFinal = false;
        for (var i = event.resultIndex; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
            if (event.results[i].isFinal) isFinal = true;
        }
        overlayTranscript.textContent = transcript;

        if (isFinal) {
            setStatus('Processing...', 'processing');
            sendCommand(transcript.trim());
        }
    };

    recognition.onerror = function (event) {
        isListening = false;
        micBtn.classList.remove('listening');
        if (event.error === 'no-speech') {
            setStatus('No speech detected. Try again.', 'error');
        } else if (event.error === 'not-allowed') {
            setStatus('Microphone access denied. Check browser permissions.', 'error');
        } else {
            setStatus('Error: ' + event.error, 'error');
        }
        setTimeout(hideOverlay, 3000);
    };

    recognition.onend = function () {
        isListening = false;
        micBtn.classList.remove('listening');
    };

    // ── Send command to backend ─────────────────────────────────────────
    function sendCommand(text) {
        fetch('/api/ai/voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            handleResponse(data);
        })
        .catch(function (err) {
            setStatus('Network error', 'error');
            overlayResponse.textContent = 'Could not reach the server.';
            setTimeout(hideOverlay, 3000);
        });
    }

    // ── Handle backend response ─────────────────────────────────────────
    function handleResponse(data) {
        var speech = data.speech || 'Done.';
        overlayResponse.textContent = speech;

        if (data.action_type === 'navigate' && data.url) {
            setStatus('Navigating...', 'success');
            speak(speech);
            setTimeout(function () {
                window.location.href = data.url;
            }, 1500);
        } else if (data.action_type === 'execute') {
            setStatus('Done', 'success');
            speak(speech);
            setTimeout(hideOverlay, 4000);
        } else if (data.action_type === 'data') {
            setStatus('', 'success');
            speak(speech);
            // Keep overlay open longer for data responses
            setTimeout(hideOverlay, Math.max(5000, speech.length * 60));
        } else if (data.action_type === 'error') {
            setStatus('', 'error');
            speak(speech);
            setTimeout(hideOverlay, 4000);
        } else {
            speak(speech);
            setTimeout(hideOverlay, 3000);
        }
    }

    // ── Activate ────────────────────────────────────────────────────────
    function startListening() {
        if (isListening) {
            recognition.stop();
            return;
        }
        try {
            recognition.start();
        } catch (e) {
            // Already started
        }
    }

    // Mic button click
    micBtn.addEventListener('click', function (e) {
        e.preventDefault();
        startListening();
    });

    // Keyboard shortcut: Ctrl + Shift + V
    document.addEventListener('keydown', function (e) {
        if (e.ctrlKey && e.shiftKey && e.key === 'V') {
            e.preventDefault();
            startListening();
        }
    });

    // Close overlay on click outside
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) {
            hideOverlay();
            if (isListening) recognition.stop();
            window.speechSynthesis.cancel();
        }
    });

    // Escape to close
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && overlay.classList.contains('active')) {
            hideOverlay();
            if (isListening) recognition.stop();
            window.speechSynthesis.cancel();
        }
    });

    // Load voices
    if (window.speechSynthesis) {
        window.speechSynthesis.getVoices();
        window.speechSynthesis.onvoiceschanged = function () {
            window.speechSynthesis.getVoices();
        };
    }

}());
