import os, uuid, tempfile
from flask import request, jsonify, render_template, send_file
import pathlib
from functions import *
from wiktionary import WiktionaryAudioService

from config import *

@app.route("/")
def index():
    return render_template("index.html")

@app.post("/transcribe")
def transcribe():
    lang = request.form.get('lang')
    if "audio" not in request.files:
        return jsonify(error="no audio"), 400
    webm = request.files["audio"]
    with tempfile.TemporaryDirectory() as td:
        webm_path = os.path.join(td, f"{uuid.uuid4()}.webm")
        wav_path   = os.path.join(td, "out.wav")
        webm.save(webm_path)

        # convert webm to wav and get transcription
        webm_to_wav(webm_path, wav_path)
        user_phonemes = azure_transcribe(wav_path, lang)

    score, aligned = dtw_score(REF_PHONEMES, user_phonemes)
    return jsonify(score=score, aligned=aligned)

@app.post("/set_word")
def set_word():
    global REF_PHONEMES

    data = request.get_json(silent=True) or {}
    lang = data.get('lang')
    word = data.get('word')
    if not word:
        return jsonify(error="No word provided!"), 400
    if not lang:
        return jsonify(error="No language provided!"), 400
    
    try:
        REF_PHONEMES = WIKI_SERVICE.build_phonemes(word, lang)
    except Exception as e:
        return jsonify(error=f"The word {word} is not present in {"English" if lang == "en-US" else "Spanish"}! Please try another word."), 400
    
    print("[DEBUG] REF_PHONEMES set event: " + str(REF_PHONEMES))
    return jsonify(status='ok', word=word, phonemes=len(REF_PHONEMES))

@app.get("/word_audio")
def word_audio():
    word = request.args.get("word")
    lang = request.args.get("lang")

    if not word:
        return jsonify(error=f"Not a word"), 400

    wav_path = pathlib.Path("cache/" + lang + f"/{word}.wav")
    if not wav_path.exists():
        return jsonify(error=f"No word found"), 400

    return send_file(wav_path, mimetype="audio/wav", as_attachment=False)

def clear_cache():
    cache = pathlib.Path(CACHE_DIR).resolve()
    if cache.is_dir():
        # remove every file inside the cache
        for entry in cache.iterdir():
            entry.unlink()

if __name__ == "__main__":

    CACHE_DIR = "cache"
    WIKI_SERVICE = WiktionaryAudioService(CACHE_DIR, 60 * 30) # 30 minute cache
    REF_PHONEMES = []

    # clear_cache() # clear cache folder on server startup

    app.run(host="0.0.0.0", port=1010, debug=True)
