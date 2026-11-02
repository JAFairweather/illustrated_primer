import io
import struct
import unittest
import wave

import notebook_voice as voice


class Samples(unittest.TestCase):
    def test_wav_reply_drops_header_and_trailing_chunk(self):
        out = io.BytesIO()
        with wave.open(out, 'wb') as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000), w.writeframes(b'\1\0'*100)
        c2pa = b'C2PA'+struct.pack('<I', 6)+b'\x7f'*6
        self.assertEqual(voice.samples(out.getvalue()+c2pa), (b'\1\0'*100, 24000))

    def test_raw_pcm_is_kept(self):
        self.assertEqual(voice.samples(b'\1\0'*4), (b'\1\0'*4, voice.GEMINI_RATE))


if __name__ == '__main__':
    unittest.main()
