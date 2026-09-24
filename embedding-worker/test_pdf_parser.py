import unittest

from pdf_parser import chunk_text


class ChunkTextTests(unittest.TestCase):
    def test_preserves_text_and_respects_chunk_limit(self):
        chunks = list(chunk_text("First paragraph.\n\nSecond paragraph.", max_chars=20))

        self.assertEqual(chunks, ["First paragraph.", "Second paragraph."])
        self.assertTrue(all(len(chunk) <= 20 for chunk in chunks))

    def test_splits_long_paragraph(self):
        chunks = list(chunk_text("abcdefghij", max_chars=4))

        self.assertEqual(chunks, ["abcd", "efgh", "ij"])


if __name__ == "__main__":
    unittest.main()
