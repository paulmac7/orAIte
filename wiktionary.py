from flask import *
import requests, re, time, pathlib

from config import *
from functions import *

class WiktionaryAudioService:
    filePattern = re.compile(r"File:([^\"'<>\s]+?\.(?:ogg|oga|wav|mp3))", re.IGNORECASE) # from File:name.ext, returns name.ext

    def __init__(self, cache_dir, cache_ttl_secs):
        self.cache_dir = pathlib.Path(cache_dir)

        # add cache cuz otherwise youd ask wikipedia way too much
        self._CACHE = {}  # structure: (expires_epoch, metadata)
        self.CACHE_TTL_SECONDS = cache_ttl_secs # how long before it expires

    # returns none if key is missing/expired
    def _cache_get(self, key):
        item = self._CACHE.get(key)

        # not cached
        if not item:
            return None
        
        # cached
        exp, val = item
        if time.time() > exp: # if old, get rid of it and return nothing
            self._CACHE.pop(key, None)
            return None
        return val
    
    def _cache_set(self, key, val):
        self._CACHE[key] = (time.time() + self.CACHE_TTL_SECONDS, val)

    def _get_wiktionary_html(self, title: str) -> str:
        # retrieves html
        url = f"https://en.wiktionary.org/api/rest_v1/page/html/{requests.utils.quote(title)}"
        r = SESSION.get(url, timeout=15)
        r.raise_for_status()
        return r.text

    def _extract_audio_filenames(self, html: str):
        files = self.filePattern.findall(html)
        
        # files has the File: stripped so we gotta add it back
        uniq = []
        seen = set()
        for f in files:
            name = "File:" + f
            # no duplicates
            if name.lower() not in seen:
                seen.add(name.lower())
                uniq.append(name)

        # return a nice list of all audio filenames present in the page
        return uniq

    def _resolve_file_url(self, file_title: str, host: str):
        # turn File::something.ogg into an actual URL
        api = f"https://{host}/w/api.php"
        params = {
            "action": "query",
            "titles": file_title,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "format": "json",
        }
        
        r = SESSION.get(api, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return None

        # pages is dict keyed by pageid; pull first
        page = next(iter(pages.values()))
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            return None

        return {
            "url": info.get("url"),
            "mime": info.get("mime"),
            "size": info.get("size"),
            "width": info.get("width"),
            "height": info.get("height"),
            "source": host,
        }

    # get the audio url
    def _get_first_audio_url(self, word: str, lang: str) -> str | None:
        # give the file if cached
        lang_short = lang[:2].lower()
        cache_key = f"audio::{word.lower()}::{lang_short}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        # otherwise, if not in cache...

        # extract html
        html = self._get_wiktionary_html(word)
        file_titles = self._extract_audio_filenames(html)



        # resolve titles trying the appropriate language wiktionary
        url = {}
        for ft in file_titles:
            f = ft[5:].lower().replace(word, "")

            if lang_short == "en" and (("(eng)" in f) or ("en" in f)):
                print(f"[DEBUG]: resolving file {ft} with truncated {f} for language {lang}")
                url = self._resolve_file_url(ft, "en.wiktionary.org")
            elif lang_short == "es" and (("(esp)" in f) or ("es" in f) or ("(spa)" in f) or ("sp" in f)):
                print(f"[DEBUG]: resolving file {ft} with truncated {f} for language {lang}")
                url = self._resolve_file_url(ft, "es.wiktionary.org")

            if url and url.get("url"):
                self._cache_set(cache_key, url.get("url"))
                return url.get("url")
        
        # if we reached here we failed :( so just return none
        self._cache_set(cache_key, None)
        return None

    def build_phonemes(self, word, lang):
        # only if the file doesn't exist do we ask wiktionary to download
        if (not pathlib.Path("cache/" + lang + "/" + word + ".wav").exists()):
            # if no url, then clearly no wiktionary audio
            url = self._get_first_audio_url(word, lang)
            if not url:
                raise RuntimeError(f"No Wiktionary audio found for '{word}'")

            # otherwise were ready to roll and create this file
            audio_bytes = SESSION.get(url, timeout=30).content

            ogg_path = self.cache_dir / lang / f"{word}.ogg"
            wav_path = self.cache_dir / lang / f"{word}.wav"

            with open(ogg_path, "wb") as f:
                f.write(audio_bytes)

            print(f"[diag] wrote {ogg_path} ({os.path.getsize(ogg_path)} bytes) from {url}")

            ogg_to_wav(ogg_path, wav_path)

        wav_path = self.cache_dir / lang / f"{word}.wav"

        return azure_transcribe(str(wav_path), lang)