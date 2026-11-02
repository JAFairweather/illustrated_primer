"""The Primer's narrator: each line of a story as speech from Gemini's TTS, for the R1 to play in the earbuds.

James picked Gemini 3.8 Flash-Lite TTS with the Sulafat voice by ear on 2026-10-31 (the bake-off in Drive, "Primer
voice bake-off"). speech() returns a WAV the R1's r1-sayd plays as is: mono 16-bit at its Piper rate with a 44-byte
header, since it streams the samples after the header straight into the earbuds. Calls go in the shared Gemini
ledger; a 429 holds only voice calls (hold-until-voice), and a line with no audio is spoken by Piper on the R1.
"""
import base64
import hashlib
import io
import json
import os
import threading
import wave

import numpy as np

import notebook_image_model as gm

MODEL = os.environ.get('HERD_BOARD_VOICE_MODEL', 'gemini-3.8-flash-lite-tts')
VOICE = os.environ.get('HERD_BOARD_VOICE', 'Sulafat')
RATE = 22050  # r1-sayd's rate: Piper en_US-lessac-medium's sample rate
GEMINI_RATE = 24000
# Only the line itself is sent: Gemini's TTS read a style paragraph above the line aloud (every short line, 2026-11-01
# 07:26), James wants no instructions in what is spoken, and this model refuses a systemInstruction (HTTP 400).
STYLE = ''
# A clip longer than LEAD+SPOKEN seconds a word carries words not in the line (the read-aloud style ran 15-20 s over;
# a short line told slowly runs 4.6-6.4 s: "The end.", "James, once upon a time...").
LEAD, SPOKEN = 6, 0.7
PAUSE = 1.2  # seconds of quiet after the question is read back, before the story begins
HELD = 'hold-until-voice'
CACHE = os.path.expanduser('~/.cache/herd-board/voice')
_making = set()  # remembered lines being made now


def resample(pcm, src=GEMINI_RATE, dst=RATE):
    """16-bit mono samples from src to dst Hz: a short low-pass, then linear interpolation."""
    x = np.frombuffer(pcm, dtype='<i2').astype(np.float32)
    if src == dst or not len(x):
        return x.astype('<i2').tobytes()
    if dst < src:
        cut = dst/src/2*0.9
        n = np.arange(-16, 17)
        taps = np.sinc(2*cut*n)*np.hamming(len(n))
        x = np.convolve(x, taps/taps.sum(), mode='same')
    t = np.arange(int(len(x)*dst/src))*src/dst
    y = np.interp(t, np.arange(len(x)), x)
    return np.clip(np.round(y), -32768, 32767).astype('<i2').tobytes()


def wav(pcm, rate=RATE):
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def speech(text, timeout=30):
    """text spoken by the narrator as WAV bytes at RATE, or None while voice calls are held, nothing came back or the
    clip runs too long for its words (Piper says the line then)."""
    if not text.strip() or gm._held(HELD):
        return None
    body = json.dumps({'contents': [{'parts': [{'text': text}]}],
                       'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {
                           'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': VOICE}}}}}).encode()
    d = gm._post(MODEL, body, timeout, name='herd-board-voice', held=HELD)
    parts = ((d.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []
    pcm = b''.join(base64.b64decode(p['inlineData']['data']) for p in parts if 'inlineData' in p)
    if not pcm or len(pcm)/2/GEMINI_RATE > LEAD+SPOKEN*len(text.split()):
        return None
    return wav(resample(pcm))


def paused(clip, seconds=PAUSE):
    """A WAV from wav() with seconds of silence after its words."""
    return wav(clip[44:]+b'\0\0'*int(RATE*seconds))


def remembered(text):
    """The speech of a line said every time (the opening), kept on disk: the WAV when kept, else None while it is
    made in the background for next time."""
    name = os.path.join(CACHE, hashlib.sha256('\n'.join((MODEL, VOICE, STYLE, text)).encode()).hexdigest()+'.wav')
    try:
        with open(name, 'rb') as f:
            return f.read()
    except OSError:
        if name in _making:
            return None
        _making.add(name)

    def make():
        try:
            clip = speech(text)
            if clip:
                os.makedirs(CACHE, exist_ok=True)
                with open(name+'.new', 'wb') as f:
                    f.write(clip)
                os.replace(name+'.new', name)
        except Exception:  # the opening is said by Piper until a call succeeds
            pass
        finally:
            _making.discard(name)
    threading.Thread(target=make, daemon=True).start()
