import json, subprocess
import azure.cognitiveservices.speech as speechsdk

from config import *

# helper to convert ogg to wav
def ogg_to_wav(in_ogg: str, out_wav: str):
    subprocess.run(
        ["ffmpeg", "-y", "-i", in_ogg, "-ar", "16000", "-ac", "1", out_wav],
        check=True
    )

# helper to convert webm to wav
def webm_to_wav(in_webm: str, out_wav: str):
    subprocess.run(
            ["ffmpeg", "-y", "-i", in_webm,
             "-ar", "16000", "-ac", "1", out_wav],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True,
        )

# returns phonemes from provided wav file
def azure_transcribe(wav_path, lang):
    speech_config = speechsdk.SpeechConfig(subscription=AZ_KEY, region=REGION)
    speech_config.output_format = speechsdk.OutputFormat.Detailed

    words_audio_config = speechsdk.AudioConfig(filename=wav_path)

    words_speech_recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=words_audio_config,
        language=lang,
    )

    # get transcription
    words = words_speech_recognizer.recognize_once()
    ref = words.text

    # and then break it down into phonemes
    pronunciation_audio_config = speechsdk.AudioConfig(filename=wav_path)  

    pronunciation_speech_recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=pronunciation_audio_config,
        language="en-US",
    )

    pronunciation_config = speechsdk.PronunciationAssessmentConfig(
        reference_text=ref,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
        enable_miscue=True,
    )
    pronunciation_config.apply_to(pronunciation_speech_recognizer)

    result = pronunciation_speech_recognizer.recognize_once()

    json_result = result.properties.get(
        speechsdk.PropertyId.SpeechServiceResponse_JsonResult
    )
    data = json.loads(json_result)

    phonemes = []
    for word in data.get("NBest", [{}])[0].get("Words", []):
        for p in word.get("Phonemes", []):
            phonemes.append({
                "phoneme": p.get("Phoneme", ""),
                "offsetMs": int(p.get("Offset", 0)) // 10000
            })

    return phonemes

# shows similarity + per phoneme timing error
def dtw_score(ref, usr):
    n, m = len(ref), len(usr)
    INF = 10 ** 9

    # dp matrix:
    d = [[INF] * (m + 1) for _ in range(n + 1)]
    d[0][0] = 0

    for i in range(1, n + 1):
        d[i][0] = i
    for j in range(1, m + 1):
        d[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub_cost = 0 if ref[i-1]["phoneme"] == usr[j-1]["phoneme"] else 1
            d[i][j] = min(
                d[i-1][j] + 1,        # deletion (ref only)
                d[i][j-1] + 1,        # insertion (usr only)
                d[i-1][j-1] + sub_cost  # match/sub
            )

    max_dist = max(n, m) if max(n, m) else 1
    similarity = ((max_dist - d[n][m]) / max_dist) * 100

    # create list that shows both sides via backtrace
    aligned = []
    i, j = n, m
    while i > 0 or j > 0:
        # prefer diagonal when tied (more intuitive alignment)
        if i > 0 and j > 0:
            sub_cost = 0 if ref[i-1]["phoneme"] == usr[j-1]["phoneme"] else 1
            if d[i][j] == d[i-1][j-1] + sub_cost:
                ref_p = ref[i-1]
                usr_p = usr[j-1]
                aligned.append({
                    "ref": ref_p["phoneme"],
                    "usr": usr_p["phoneme"],
                    "offsetErrorMs": abs(ref_p["offsetMs"] - usr_p["offsetMs"]),
                    "kind": "match" if sub_cost == 0 else "sub"
                })
                i -= 1
                j -= 1
                continue

        # deletion (ref phoneme has no user counterpart)
        if i > 0 and d[i][j] == d[i-1][j] + 1:
            aligned.append({
                "ref": ref[i-1]["phoneme"],
                "usr": None,
                "offsetErrorMs": None,
                "kind": "del"
            })
            i -= 1
            continue

        # insertion (user phoneme has no ref counterpart)
        if j > 0 and d[i][j] == d[i][j-1] + 1:
            aligned.append({
                "ref": None,
                "usr": usr[j-1]["phoneme"],
                "offsetErrorMs": None,
                "kind": "ins"
            })
            j -= 1
            continue

        # just in case to prevent infinite loops
        if i > 0: i -= 1
        elif j > 0: j -= 1

    aligned.reverse()
    return similarity, aligned