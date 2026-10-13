/* app.js - Riff dashboard (telemetry + exercise picker + neck guide)
   Audio capture is SERVER-SIDE (sounddevice/M-Track). The browser connects to
   the WS and plots telemetry + guides on the neck.

   PRESERVED CONTRACTS: all getElementById targets, neck.js API, WS messages.
   ADDED (UI only): tab navigation, exercises/settings views, event counter.
   */
(() => {
    const wsProto = location.protocol === "https:" ? "wss://" : "ws://";
    const wsUrl = wsProto + location.host + "/ws";
    let ws = null;
    let sessionActive = false;
    let currentExercise = "scale_e_minor_001";
    let selectedGain = 4.0;
    let taskNotes = [];
    let playedIndex = 0;
    let lastCents = null;
    let eventCount = 0;
    let matchHoldTimer = null;
    let matchFadeTimer = null;
    let selectedDevice = null;   // from /api/devices (P1-A)
    let selectedDeviceChannels = 0;  // channels of the chosen device (P1-A)
    let selectedChannel = 0;     // derived from device channels; 0=CH1, 1=CH2

    // ---- DOM (contract targets) ----
    const statusEl = document.getElementById('status');
    const statusDot = statusEl.querySelector('.status-dot');
    const exerciseSelect = document.getElementById('exercise-select');
    const exerciseTargetEl = document.getElementById('exercise-target');
    const bpmValueEl = document.getElementById('current-task');
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    const progressionEl = document.getElementById('progression');
    const skillListEl = document.getElementById('skill-list');
    const recentSessionsEl = document.getElementById('recent-sessions');
    const neckEl = document.getElementById('neck');
    const neckHintEl = document.getElementById('neck-hint');
    const pitchNoteEl = document.getElementById('pitch-note');
    const pitchFreqEl = document.getElementById('pitch-frequency');
    const pitchCentsEl = document.getElementById('pitch-cents');
    const pitchCentsValueEl = document.getElementById('pitch-cents-value');
    const pitchConfEl = document.getElementById('pitch-confidence');
    const pitchOnsetEl = document.getElementById('pitch-onset');
    const meterCh1El = document.getElementById('meter-ch1');
    const meterCh2El = document.getElementById('meter-ch2');
    const meterCh1ValueEl = document.getElementById('meter-ch1-value');
    const meterCh2ValueEl = document.getElementById('meter-ch2-value');
    const teacherActionEl = document.getElementById('teacher-action');
    const teacherTempoEl = document.getElementById('teacher-tempo');
    const teacherReasonEl = document.getElementById('teacher-reason');
    const teacherFeedbackEl = document.getElementById('teacher-feedback');
    const teacherSourceEl = document.getElementById('teacher-source');
    const debugLogEl = document.getElementById('debug-log');
    // new UI-only targets
    const exerciseListEl = document.getElementById('exercise-list');
    const settingsGainEl = document.getElementById('settings-gain');
    const eventLogCountEl = document.getElementById('event-log-count');

    window.__riff = { setCents: (c) => { lastCents = c; } };

    function log(msg) {
        debugLogEl.textContent += `[${new Date().toLocaleTimeString()}] ${msg}\n`;
        debugLogEl.scrollTop = debugLogEl.scrollHeight;
    }
    function bumpEvent(msg) {
        eventCount++;
        if (eventLogCountEl) eventLogCountEl.textContent = `${eventCount} events`;
    }

    function setStatus(connected) {
        sessionActive = connected;
        statusEl.children[1].textContent = connected ? "Connected" : "Disconnected";
        statusDot.style.background = connected ? "var(--success)" : "var(--danger)";
        statusDot.style.boxShadow = connected
            ? "0 0 0 4px var(--success-soft)"
            : "0 0 0 4px var(--danger-soft)";
        btnStart.disabled = connected;
        btnStop.disabled = !connected;
    }

    // ---- tab navigation (UI only) ----
    const navButtons = Array.from(document.querySelectorAll('[data-nav]'));
    function showView(name) {
        navButtons.forEach(b => b.classList.toggle('active', b.dataset.nav === name));
        ['coach', 'progress', 'exercises', 'settings'].forEach(v => {
            const el = document.getElementById('view-' + v);
            if (el) el.hidden = (v !== name);
        });
    }
    navButtons.forEach(b => b.addEventListener('click', () => showView(b.dataset.nav)));

    // gain helpers (shared between session bar and settings)
    function makeGainOption(v) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = '×' + v;
        btn.classList.toggle('selected', v === selectedGain);
        btn.addEventListener('click', () => { selectedGain = v; syncGainUI(); });
        return btn;
    }
    function syncGainUI() {
        // selection highlight in both session bar and settings
        document.querySelectorAll('.gain-option').forEach(el => {
            el.classList.toggle('selected', el.dataset.gain == selectedGain);
        });
        document.getElementById('session-controls').querySelectorAll('.gain-btn').forEach(el => {
            el.classList.toggle('selected', el.dataset.gain == selectedGain);
        });
    }

    // ---- exercises + progress ----
    async function loadExercises() {
        try {
            const ex = await fetch('/api/exercises').then(r => r.json());
            exerciseSelect.innerHTML = '<option value="">Choose an exercise</option>';
            if (exerciseListEl) exerciseListEl.innerHTML = '';
            ex.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.name;
                exerciseSelect.appendChild(opt);
                // exercises view card
                if (exerciseListEl) {
                    const item = document.createElement('div');
                    item.className = 'exercise-item';
                    const notes = (e.target_notes || []).join(' ');
                    item.innerHTML = `<div><div class="ex-name">${e.name}</div>
                        <div class="ex-meta">${notes}</div></div>
                        <div class="ex-meta">${e.target_bpm ?? '—'} BPM · difficulty ${e.difficulty ?? 1}</div>`;
                    item.style.cursor = 'pointer';
                    item.addEventListener('click', () => {
                        exerciseSelect.value = e.id;
                        selectExercise();
                        showView('coach');
                    });
                    exerciseListEl.appendChild(item);
                }
            });
            if (ex.length) {
                currentExercise = ex[0].id;
                exerciseSelect.value = currentExercise;
                selectExercise();
            }
            log(`Loaded ${ex.length} exercises`);
        } catch (e) { log(`Exercises failed: ${e}`); }
    }

    async function selectExercise() {
        currentExercise = exerciseSelect.value;
        if (!currentExercise) return;
        try {
            const e = await fetch(`/api/exercises/${currentExercise}`).then(r => r.json());
            taskNotes = e.target_notes || [];
            exerciseTargetEl.textContent = e.name;
            bpmValueEl.textContent = e.target_bpm ?? "--";
            renderNotePills();
            renderNeck();
        } catch (err) { log(`Exercise load failed: ${err}`); }
        loadProgress();
    }

    function renderNotePills() {
        progressionEl.innerHTML = '';
        if (!taskNotes.length) {
            progressionEl.innerHTML = '<span class="empty-state">Select an exercise to begin.</span>';
            return;
        }
        taskNotes.forEach((n, i) => {
            const pill = document.createElement('span');
            pill.textContent = n;
            pill.classList.add('note-pill');
            pill.dataset.index = i;
            if (i === playedIndex) pill.classList.add('current');
            progressionEl.appendChild(pill);
        });
        updatePills();
    }
    function updatePills() {
        progressionEl.querySelectorAll('[data-index]').forEach(p => {
            p.classList.toggle('current', parseInt(p.dataset.index) === playedIndex);
        });
    }

    async function loadProgress() {
        try {
            const p = await fetch('/api/progress').then(r => r.json());
            renderSkills(p.skills || {});
            renderRecent(p.recent || [], p.exercises || {});
        } catch (e) { log(`Progress failed: ${e}`); }
    }

    function average(arr) { return arr.reduce((a, b) => a + b, 0) / arr.length; }

    function renderSkills(skills) {
        if (!skillListEl) return;
        skillListEl.innerHTML = '';
        const names = Object.keys(skills);
        if (!names.length) {
            skillListEl.innerHTML = '<div class="skill-card"><div class="skill-name">No practice yet</div><div class="skill-value">—</div></div>';
            return;
        }
        const dims = ['note_accuracy', 'timing_accuracy', 'consistency'];
        dims.forEach(dim => {
            const card = document.createElement('div');
            card.className = 'skill-card';
            const vals = names.map(n => skills[n][dim]).filter(v => v != null);
            const val = vals.length ? Math.round(average(vals) * 100) + '%' : '—';
            card.innerHTML = `<div class="skill-name">${dim.replace('_', ' ')}</div><div class="skill-value">${val}</div>`;
            skillListEl.appendChild(card);
        });
    }

    function renderRecent(recent, exercises) {
        if (!recentSessionsEl) return;
        recentSessionsEl.innerHTML = '';
        if (!recent.length) {
            recentSessionsEl.textContent = 'No sessions yet.';
            return;
        }
        recent.slice(0, 5).forEach(r => {
            const div = document.createElement('div');
            const name = exercises[r.exercise_id] ? exercises[r.exercise_id].name : r.exercise_id;
            div.textContent = `${name} — notes ${Math.round((r.note_accuracy || 0) * 100)}% · BPM ${r.performed_bpm ?? '—'}/${r.target_bpm ?? '—'}`;
            recentSessionsEl.appendChild(div);
        });
    }

    // ---- neck guide ----
    function renderNeck() {
        if (!window.Neck || !taskNotes.length) return;
        window.Neck.render(neckEl, taskNotes);
        neckHintEl.textContent = "Target · Next · Played";
        playedIndex = 0;
        updatePills();
        markNext();
    }
    function markNext() {
        if (taskNotes.length && window.Neck) {
            window.Neck.highlightNext(neckEl, taskNotes[Math.min(playedIndex, taskNotes.length - 1)]);
        }
    }
    function onNotePlayed(note) {
        if (!taskNotes.length || !window.Neck) return;
        window.Neck.clearPlaying(neckEl);
        window.Neck.playNote(neckEl, note);
        window.Neck.highlightCurrent(neckEl, note, note);
        const expected = taskNotes[playedIndex];
        // UX: unambiguous right/wrong feedback, held ~1.6s so the player can read it
        const matchEl = document.getElementById('pitch-match');
        if (matchEl) {
            clearTimeout(matchHoldTimer);
            clearTimeout(matchFadeTimer);
            matchEl.classList.remove('fade');
            if (expected && expected !== note) {
                matchEl.hidden = false;
                matchEl.className = 'pitch-match wrong';
                matchEl.textContent = `You played ${note} — expected ${expected}`;
            } else if (expected === note) {
                matchEl.hidden = false;
                matchEl.className = 'pitch-match right';
                matchEl.textContent = `${note} — correct`;
            } else {
                matchEl.hidden = true;
            }
            // hold the verdict visible ~1.6s, then fade out (reset by the next note)
            matchHoldTimer = setTimeout(() => {
                matchEl.classList.add('fade');
                matchFadeTimer = setTimeout(() => { matchEl.hidden = true; }, 200);
            }, 1600);
        }
        // advance only on hit (unchanged behavior)
        if (expected === note) {
            playedIndex = Math.min(playedIndex + 1, taskNotes.length - 1);
        } else {
            const idx = taskNotes.indexOf(note);
            if (idx >= 0) playedIndex = Math.min(idx + 1, taskNotes.length - 1);
        }
        markNext();
        updatePills();
    }

    // ---- telemetry ----
    function updatePitch(note, freq, conf, onset) {
        pitchNoteEl.textContent = note || "--";
        pitchFreqEl.textContent = freq != null ? String(freq) : "--";
        pitchConfEl.textContent = conf != null ? conf.toFixed(2) : "--";
        pitchOnsetEl.textContent = onset ? "yes" : "no";
    }
    function setCents(cents) {
        if (cents == null) { if (pitchCentsValueEl) pitchCentsValueEl.textContent = "--"; return; }
        if (pitchCentsValueEl) pitchCentsValueEl.textContent = (cents > 0 ? "+" : "") + cents.toFixed(0);
        const pct = 50 + Math.max(-50, Math.min(50, cents)) / 50 * 48;
        pitchCentsEl.style.left = pct + '%';
    }
    function setChannelMeter(fillEl, valueEl, db) {
        if (!fillEl) return;
        if (db == null) { if (valueEl) valueEl.textContent = "--"; fillEl.style.width = "0%"; return; }
        if (valueEl) valueEl.textContent = db.toFixed(1);
        const pct = Math.max(0, Math.min(100, (db + 60) / 60 * 100));
        fillEl.style.width = pct + '%';
    }

    function handleMessage(data) {
        switch (data.type) {
            case "pitch":
                updatePitch(data.note, data.frequency, data.confidence, data.onset);
                setCents(data.cents ?? null);
                break;
            case "note_event":
                log(`note_event  ${data.note}`);
                bumpEvent();
                onNotePlayed(data.note);
                break;
            case "meter":
                setChannelMeter(meterCh1El, meterCh1ValueEl, data.rms_db ?? data.ch1);
                if (data.ch2 != null) setChannelMeter(meterCh2El, meterCh2ValueEl, data.ch2);
                break;
            case "meter_message":
            case "channels_dbfs":
                if (data.channels) {
                    setChannelMeter(meterCh1El, meterCh1ValueEl, data.channels[0]);
                    setChannelMeter(meterCh2El, meterCh2ValueEl, data.channels[1]);
                }
                break;
            case "teacher":
                teacherActionEl.textContent = data.action || "Ready";
                teacherTempoEl.textContent = data.tempo != null ? String(data.tempo) : "--";
                teacherReasonEl.textContent = data.reason || "--";
                teacherFeedbackEl.textContent = data.spoken_feedback || "—";
                teacherSourceEl.textContent = data.source || "--";
                bumpEvent();
                log(`teacher     ${data.action} (${data.source})`);
                break;
            case "attempt_result": {
                // One attempt closed: show the 4 dims (no score) and reset the guide.
                const p = data.performance || {};
                const pct = v => v != null ? Math.round(v * 100) + '%' : '--';
                neckHintEl.textContent = `Attempt ${data.attempt} · notes ${pct(p.note_accuracy)}`
                    + ` · timing ${pct(p.timing_accuracy)}`
                    + (p.performed_bpm != null ? ` · ${Math.round(p.performed_bpm)} BPM` : '');
                log(`attempt     #${data.attempt} notes=${pct(p.note_accuracy)} timing=${pct(p.timing_accuracy)}`);
                bumpEvent();
                playedIndex = 0;
                markNext();
                updatePills();
                break;
            }
            case "session_state":
                if (data.status === "running") {
                    bpmValueEl.textContent = data.target_bpm ?? bpmValueEl.textContent;
                    setStatus(true);
                }
                break;
            case "error":
                log(`ERROR: ${data.message}`);
                bumpEvent();
                break;
            default: break;
        }
    }

    // ---- websocket ----
    function connect() {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => { setStatus(true); log("Connected"); };
        ws.onmessage = (e) => {
            try { handleMessage(JSON.parse(e.data)); }
            catch (err) { log(`Bad msg: ${err}`); }
        };
        ws.onclose = (ev) => { setStatus(false); log(`Closed (${ev.code})`); setTimeout(connect, 2500); };
        ws.onerror = () => log("WS error");
    }

    async function loadDevices() {
        try {
            const devs = await fetch('/api/devices').then(r => r.json());
            if (!devs.length) return;
            // Prefer the M-Track/M-Audio interface (the target hardware), else most channels.
            let choose = devs.find(d => /M-?Track|M-Audio/i.test(d.name || ''))
                || devs.reduce((a, b) => (b.channels > a.channels ? b : a), devs[0]);
            selectedDevice = choose.index;
            selectedDeviceChannels = choose.channels || 0;
            // Derive the channel from the device's channel count (P1-A: no blind default).
            // Stereo (>=2ch): default to CH2 (index 1, the Instrument/Hi-Z input on the M-Track).
            // Mono (1ch): only CH1 (index 0) exists.
            selectedChannel = selectedDeviceChannels >= 2 ? 1 : 0;
            log(`Device: ${choose.name} (idx ${choose.index}, ${choose.channels}ch) → channel ${selectedChannel}`);
        } catch (e) { log(`Devices failed: ${e}`); }
    }

    function startSession() {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        playedIndex = 0;
        renderNeck();
        ws.send(JSON.stringify({
            type: "start_session",
            exercise_id: currentExercise,
            channel: selectedChannel, sample_rate: 44100, block_size: 1024,
            device: selectedDevice, gain: selectedGain, amplitude_floor: 0.01
        }));
        log(`Started ${currentExercise} (device ${selectedDevice}, ch ${selectedChannel}, gain x${selectedGain})`);
    }

    // ---- controls ----
    exerciseSelect.addEventListener('change', selectExercise);
    btnStart.addEventListener('click', startSession);
    btnStop.addEventListener('click', () => {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop_session" }));
        setStatus(false);
        loadProgress();
    });

    // gain selector (session bar) — appended as before: preserved contract
    const gainWrap = document.createElement('div');
    gainWrap.className = 'session-exercise';
    gainWrap.innerHTML = `<label for="gain-select">SENSITIVITY</label>
        <select id="gain-select" class="gain-select">
            <option value="1">×1</option><option value="2">×2</option>
            <option value="4" selected>×4 (recommended)</option>
            <option value="8">×8</option><option value="16">×16</option>
        </select>`;
    document.getElementById('session-controls').appendChild(gainWrap);
    gainWrap.querySelector('#gain-select').addEventListener('change', (e) => {
        selectedGain = parseFloat(e.target.value);
        syncGainUI();
    });

    // settings view gain buttons
    if (settingsGainEl) {
        [1, 2, 4, 8, 16].forEach(v => {
            const btn = makeGainOption(v);
            btn.dataset.gain = v;
            btn.classList.add('gain-option');
            settingsGainEl.appendChild(btn);
        });
        syncGainUI();
    }

    // init
    setStatus(false);
    connect();
    loadExercises();
    loadDevices();
    loadProgress();
    showView('coach');
})();