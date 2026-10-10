import unittest

import lyrics


class LyricsStateTests(unittest.TestCase):
    def test_marks_song_complete_after_clip_end(self):
        _, _, _, finished = lyrics.lyric_state(lyrics.LEAD_IN + lyrics.CLIP_LENGTH + 0.1)
        self.assertTrue(finished)

    def test_stays_active_during_song(self):
        _, _, _, finished = lyrics.lyric_state(lyrics.LEAD_IN + 5.0)
        self.assertFalse(finished)


if __name__ == '__main__':
    unittest.main()
