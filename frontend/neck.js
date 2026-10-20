/* neck.js - real-time guitar fretboard (SVG) showing exercise target notes
   and the currently-played note. Pure frontend rendering; reads note names
   reported by the backend via WebSocket. */
(() => {
    // Standard tuning, 6th string (low E) first.
    const STRINGS = ["E2", "A2", "D3", "G3", "B3", "E4"];
    const FRETS = 12;            // 0 (nut) .. 12
    const BASE_SEMIS = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

    function noteFreq(name) {
        const m = name.match(/^([A-G])([#b]?)(-?\d+)$/);
        if (!m) return null;
        let semis = BASE_SEMIS[m[1]];
        if (m[2] === '#') semis += 1;
        else if (m[2] === 'b') semis -= 1;
        const midi = 12 * (parseInt(m[3]) + 1) + semis;
        return 440 * Math.pow(2, (midi - 69) / 12);
    }

    // Find (stringIdx, fret) for a note: pick the lowest-fret position on any string.
    function positionFor(note) {
        const f = noteFreq(note);
        if (f == null) return null;
        let best = null, bestFret = 99, bestString = 99;
        STRINGS.forEach((open, si) => {
            const of = noteFreq(open);
            for (let fret = 0; fret <= FRETS; fret++) {
                const cand = of * Math.pow(2, fret / 12);
                // semitone distance in cents
                const cents = Math.abs(1200 * Math.log2(f / cand));
                if (cents < 25 && fret <= bestFret) {
                    // prefer higher string (lower pitch position is standard, but
                    // lowest fret matters most for open-position teaching)
                    if (fret < bestFret || (fret === bestFret && si > bestString)) {
                        best = { string: si, fret }; bestFret = fret; bestString = si;
                    }
                }
            }
        });
        return best;
    }

    // Render SVG neck. Container: #neck.
    function render(container, targetNotes) {
        const W = 460, H = 210;
        const marginL = 20, marginT = 26, marginB = 28;
        const stringH = (H - marginT - marginB) / (STRINGS.length - 1);
        const nFrets = FRETS;
        const fretW = (W - marginL - 14) / nFrets;

        let svg = `<svg viewBox="0 0 ${W} ${H}" class="neck-svg" xmlns="http://www.w3.org/2000/svg">`;
        // fretboard background (dark rosewood)
        svg += `<rect x="${marginL}" y="${marginT-16}" width="${W-marginL-14}" height="${H-marginT-marginB+16}" fill="#241a12" rx="6"/>`;
        svg += `<rect x="${marginL}" y="${marginT-16}" width="${W-marginL-14}" height="18" fill="#1a120c" opacity="0.6" rx="6"/>`;
        svg += `<rect x="${marginL}" y="${H-marginB-2}" width="${W-marginL-14}" height="18" fill="#1a120c" opacity="0.6" rx="6"/>`;

        // frets (vertical lines, brushed metal)
        for (let f = 0; f <= nFrets; f++) {
            const x = marginL + f * fretW;
            svg += `<line x1="${x}" y1="${marginT-16}" x2="${x}" y2="${H-marginB}" stroke="#3d434d" stroke-width="${f===0?3:1.4}"/>`;
            if (f > 0 && f % 2 === 0) {
                svg += `<text x="${x + fretW/2}" y="${H - 6}" font-size="9" fill="#5f6875" text-anchor="middle">${f}</text>`;
            }
        }
        // inlay dots (frets 3,5,7,9)
        [3,5,7,9].forEach(f => {
            const x = marginL + f*fretW + fretW/2;
            for (let s=0;s<6;s++){
                if (f===7 && s!==2 && s!==3) continue;
                if (f!==7 && s!==2) continue;
                svg += `<circle cx="${x}" cy="${marginT-16 + (H-marginT-marginB)/2}" r="3.2" fill="#0d0a07" opacity="0.7"/>`;
            }
        });

        // strings (horizontal lines, bright steel; thick low)
        STRINGS.forEach((open, i) => {
            const y = marginT + i * stringH;
            const w = (i < 3) ? 1.8 : (i < 5 ? 1.3 : 1.0);
            svg += `<line x1="${marginL}" y1="${y}" x2="${W-14}" y2="${y}" stroke="#d5d8dd" stroke-width="${w}" stroke-opacity="0.8"/>`;
            svg += `<text x="${marginL-7}" y="${y+3}" font-size="8" fill="#8b94a3" text-anchor="end">${open}</text>`;
        });

        // target note dots (exercise) - blue
        const targetCol = getComputedStyle(document.body).getPropertyValue('--blue').trim() || "#5aa8ff";
        targetNotes.forEach(note => {
            const p = positionFor(note);
            if (!p) return;
            const x = marginL + (p.fret + 0.5) * fretW;
            const y = marginT + p.string * stringH;
            svg += `<circle data-note="${note}" class="neck-target" cx="${x}" cy="${y}" r="7.5" fill="none" stroke="${targetCol}" stroke-width="2" opacity="0.65">`;
            svg += `<title>${note} (${p.string+1}a corda, traste ${p.fret})</title></circle>`;
        });

        // "current note" marker - red
        svg += `<circle data-role="current" cx="0" cy="0" r="10" fill="#ff5d5d" opacity="0" stroke="#ff5d5d"/>`;
        svg += `<text data-role="current-label" x="0" y="0" font-size="11" fill="#fff" text-anchor="middle" font-weight="bold"></text>`;
        // "next to play" marker - green
        svg += `<circle data-role="next" cx="0" cy="0" r="9" fill="#3ee08f" opacity="0"/>`;
        svg += `<text data-role="next-label" x="0" y="0" font-size="10" fill="#06070a" text-anchor="middle" font-weight="bold"></text>`;

        svg += `</svg>`;
        container.innerHTML = svg;
        container._params = { marginL, marginT, stringH, fretW };
        container._positions = {};
        targetNotes.forEach(n => { container._positions[n] = positionFor(n); });
    }

    // Place a dot at a note's position.
    function coord(container, note) {
        const p = container._positions[note];
        if (!p || !container._params) return null;
        const { marginL, marginT, stringH, fretW } = container._params;
        return { x: marginL + (p.fret + 0.5) * fretW, y: marginT + p.string * stringH };
    }

    function xy(container, x, y, labelEl, circleEl, opacity) {
        if (!container) return;
        const c = container.querySelector('[data-role="current"]');
        const l = container.querySelector('[data-role="current-label"]');
        if (c && x != null) { c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('opacity', opacity==null?0.9:opacity); }
        if (l && x != null) { l.setAttribute('x', x); l.setAttribute('y', y-11); l.setAttribute('opacity', opacity==null?1:opacity); }
    }

    // Expose
    window.Neck = {
        render, positionFor, coord,
        highlightCurrent: (container, note, label) => {
            const p = coord(container, note);
            if (!p) { xy(container, null, null); return; }
            const c = container.querySelector('[data-role="current"]');
            const l = container.querySelector('[data-role="current-label"]');
            c.setAttribute('cx', p.x); c.setAttribute('cy', p.y); c.setAttribute('opacity', 0.9);
            l.setAttribute('x', p.x); l.setAttribute('y', p.y - 12); l.setAttribute('opacity', 1);
            l.textContent = label || note;
            container.classList.add('playing');
        },
        highlightNext: (container, note) => {
            const p = coord(container, note);
            const n = container.querySelector('[data-role="next"]');
            if (!n) return;
            if (!p) { n.setAttribute('opacity', 0); return; }
            n.setAttribute('cx', p.x); n.setAttribute('cy', p.y); n.setAttribute('opacity', 0.95);
        },
        playNote: (container, note) => {
            // briefly flash target dots with this note name
            container.querySelectorAll('.neck-target[data-note="'+note+'"]').forEach(d => {
                d.classList.add('hit');
                setTimeout(() => d.classList.remove('hit'), 350);
            });
        },
        clearPlaying: (container) => {
            if (!container) return;
            container.classList.remove('playing');
            const c = container.querySelector('[data-role="current"]');
            const l = container.querySelector('[data-role="current-label"]');
            if (c) c.setAttribute('opacity', 0);
            if (l) l.setAttribute('opacity', 0);
            const n = container.querySelector('[data-role="next"]');
            if (n) n.setAttribute('opacity', 0);
        }
    };
})();