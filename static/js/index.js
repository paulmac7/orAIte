let mediaRecorder, chunks = [], recording = false;
let recordBtn = document.getElementById('recBtn');
let setWordBtn = document.getElementById('setWordBtn');

let PHONEME_MAP = null;

window.SELECTED_LANG = 'en-US';

function setLang(lang) {
    window.SELECTED_LANG = lang;
    document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.lang-btn[data-lang="${lang}"]`)?.classList.add('active');
}

document.getElementById('langEn')?.addEventListener('click', () => setLang('en-US'));
document.getElementById('langEs')?.addEventListener('click', () => setLang('es-ES'))

let CURRENT_WORD = null;

const playBtn = document.getElementById('playWordBtn');
const audioEl = document.getElementById('wordAudio');

playBtn.addEventListener('click', async () => {
    if (!audioEl.src) return;
    try {
        await audioEl.play();
    } catch (e) {
        console.error(e);
    }
});

async function loadPhonemeMap() {
    if (PHONEME_MAP) return PHONEME_MAP;
    const resp = await fetch(window.PHONEME_MAP_URL);
    if (!resp.ok) throw new Error(`map load failed: ${resp.status}`);
    PHONEME_MAP = await resp.json();
    return PHONEME_MAP;
}

// grab Azure SAPI and remove any stress markers (numbers) and make it all uppercase
function normalizePhone(p) {
    if (!p) return "";
    return String(p).toUpperCase().replace(/[0-2]$/, "");
}

recordBtn.addEventListener('click', async () => {
    const word = document.getElementById('wordDisplay').textContent;
    // no empty words!
    if (word == "--") {
        document.getElementById("error").textContent = "Error: Please select a word";
        return;
    }
    if (!recording) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = e => chunks.push(e.data);
        mediaRecorder.onstop = upload;
        mediaRecorder.start();
        recordBtn.textContent = 'Stop & Analyse';
        recording = true;
    } else {
        mediaRecorder.stop();
        recordBtn.disabled = true;
        recording = false;
    }
});

setWordBtn.addEventListener('click', async () => {
    const word = document.getElementById('wordInput').value.trim();
    if (!word) {
        document.getElementById("error").textContent = "Error: Please type a word";
        return;
    }
    const loading = document.getElementById('loadingWord');
    loading.classList.add('on');

    // language handler
    const fd = new FormData();
    fd.append('word', word);
    
    const resp = await fetch('/set_word', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word, lang: window.SELECTED_LANG }), fd
    });

    const data = await resp.json();
    loading.classList.remove('on');
    if (resp.ok) {
        // alert(`Reference word set to "${data.word}"`);
        document.getElementById("wordDisplay").textContent = word;
        document.getElementById("error").textContent = "";

        const qs = new URLSearchParams({
            word: word,
            lang: window.SELECTED_LANG,
            t: Date.now()
        });

        audioEl.src = `/word_audio?${qs.toString()}`;
        playBtn.disabled = false;
    } else {
        //alert('Error: ' + (data.error || resp.statusText));
        document.getElementById("error").textContent = "Error: " + (data.error || resp.statusText);
    }
});

async function upload() {
    const blob = new Blob(chunks, { type: 'audio/webm' });
    const loading = document.getElementById('loading');
    loading.classList.add('on');
    chunks = [];
    const fd = new FormData();
    fd.append('audio', blob, 'sample.webm');
    
    // language
    fd.append('lang', window.SELECTED_LANG);

    const resp = await fetch('/transcribe', { method: 'POST', body: fd });
    const data = await resp.json();

    document.getElementById('score').textContent =
        `Accuracy: ${data.score.toFixed(1)}%`;

    const map = await loadPhonemeMap();

    const refRow = document.getElementById('refRow');
    const usrRow = document.getElementById('usrRow');
    refRow.innerHTML = '';
    usrRow.innerHTML = '';

    data.aligned.forEach(step => {
        // step.ref / step.usr are SAPI phones or null
        const refRaw = step.ref;
        const usrRaw = step.usr;

        const refSpan = document.createElement('span');
        const usrSpan = document.createElement('span');

        // show "-" for gaps so columns line up
        const refKey = normalizePhone(refRaw);
        const usrKey = normalizePhone(usrRaw);

        const refInfo = refRaw ? map[refKey] : null;
        const usrInfo = usrRaw ? map[usrKey] : null;

        refSpan.textContent = refRaw ? (refInfo?.label ?? refRaw) : '—';
        usrSpan.textContent = usrRaw ? (usrInfo?.label ?? usrRaw) : '—';

        // base styling
        refSpan.className = 'phoneme ref';
        usrSpan.className = 'phoneme usr';

        // show substitutions, insertions, deletions
        if (step.kind === 'sub') {
            refSpan.classList.add('bad');
            usrSpan.classList.add('bad');
        } else if (step.kind === 'del') {
            refSpan.classList.add('bad');
            usrSpan.classList.add('gap');
        } else if (step.kind === 'ins') {
            usrSpan.classList.add('bad');
            refSpan.classList.add('gap');
        } else {
            refSpan.classList.add('good');
            usrSpan.classList.add('good');
        }

        // timing
        /*if ((step.offsetErrorMs ?? 0) > 100) {
            refSpan.classList.add('bad');
            usrSpan.classList.add('bad');
        }*/

        // tooltips
        if (refInfo) {
            refSpan.dataset.ipa = refInfo.ipa ?? '';
            refSpan.dataset.example = refInfo.example ?? '';
            refSpan.dataset.raw = refRaw ?? '';
            // set title just in case
            refSpan.title = `IPA: ${refInfo.ipa}\nExample: ${refInfo.example}`;
        } else if (refRaw) {
            refSpan.dataset.raw = refRaw;
            refSpan.title = `SAPI: ${refRaw}`;
        }

        if (usrInfo) {
            usrSpan.dataset.ipa = usrInfo.ipa ?? '';
            usrSpan.dataset.example = usrInfo.example ?? '';
            usrSpan.dataset.raw = usrRaw ?? '';
            usrSpan.title = `IPA: ${usrInfo.ipa}\nExample: ${usrInfo.example}`;
        } else if (usrRaw) {
            usrSpan.dataset.raw = usrRaw;
            usrSpan.title = `SAPI: ${usrRaw}`;
        }

        refRow.appendChild(refSpan);
        usrRow.appendChild(usrSpan);
    });

    loading.classList.remove('on');
    recordBtn.disabled = false;
    recordBtn.textContent = 'Start Recording';
}