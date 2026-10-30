import io
import struct
import unittest

from muj_study.gemini import pdf_page_chunks
from muj_study.document_media import placeable_wmf, normalize_image


class DocumentRecoveryTests(unittest.TestCase):
    def test_oversized_pdf_chunks_split_without_losing_original_page_numbers(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import NameObject, DecodedStreamObject
        writer = PdfWriter()
        for _ in range(4):
            page = writer.add_blank_page(width=600, height=800)
            stream = DecodedStreamObject(); stream.set_data(b' ' * 5000)
            page[NameObject('/Contents')] = stream
        chunks = list(pdf_page_chunks(list(writer.pages), first=7, max_bytes=7000))
        self.assertEqual([first for _, first in chunks], [7, 8, 9, 10])
        self.assertEqual(sum(len(PdfReader(io.BytesIO(data)).pages) for data, _ in chunks), 4)
        self.assertTrue(all(len(data) <= 7000 for data, _ in chunks))

    def test_standard_wmf_gets_valid_display_bounds_and_checksum(self):
        header = struct.pack('<HHHIHIH', 1, 9, 0x300, 100, 0, 0, 0)
        window = struct.pack('<IHhh', 5, 0x020C, 1453, 1938)
        blob = header + window
        wrapped = placeable_wmf(blob)
        self.assertEqual(struct.unpack_from('<I', wrapped)[0], 0x9AC6CDD7)
        self.assertEqual(struct.unpack_from('<hhhh', wrapped, 6), (0, 0, 1938, 1453))
        checksum = 0
        for word in struct.unpack('<11H', wrapped[:22]): checksum ^= word
        self.assertEqual(checksum, 0)
        self.assertEqual(wrapped[22:], blob)

    def test_invalid_image_produces_a_controlled_error(self):
        with self.assertRaises(ValueError): normalize_image(b'bad image', 'image/png')
