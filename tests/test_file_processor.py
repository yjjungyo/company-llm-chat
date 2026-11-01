"""파일 파서 및 포맷터 단위 테스트."""

import unittest
from file_processor import (
    extract_text_from_plain_text,
    format_file_size,
    format_message_with_attachments,
    build_multimodal_request_content,
    parse_uploaded_file,
)


class MockUploadedFile:
    def __init__(self, name: str, content: bytes, mime: str = "text/plain"):
        self.name = name
        self.content = content
        self.type = mime
        self.size = len(content)

    def getvalue(self) -> bytes:
        return self.content


class TestFileProcessor(unittest.TestCase):
    def test_format_file_size(self):
        self.assertEqual(format_file_size(500), "500 B")
        self.assertEqual(format_file_size(2048), "2.0 KB")
        self.assertEqual(format_file_size(1048576 * 3), "3.0 MB")

    def test_extract_plain_text(self):
        text = extract_text_from_plain_text("안녕하세요 테스트".encode("utf-8"))
        self.assertEqual(text, "안녕하세요 테스트")

    def test_parse_uploaded_text_file(self):
        f = MockUploadedFile("sample.py", b"def hello():\n    return 'hi'", "text/x-python")
        parsed = parse_uploaded_file(f)
        self.assertEqual(parsed["name"], "sample.py")
        self.assertEqual(parsed["ext"], ".py")
        self.assertFalse(parsed["is_image"])
        self.assertIn("def hello", parsed["text"])

    def test_format_message_with_attachments(self):
        f = MockUploadedFile("data.txt", b"column1,column2\n1,2", "text/plain")
        parsed = parse_uploaded_file(f)
        msg = format_message_with_attachments("데이터 분석해줘", [parsed])
        self.assertIn("📎 **첨부 파일 (1개):**", msg)
        self.assertIn("데이터 분석해줘", msg)
        self.assertIn("<details>", msg)
        self.assertIn("column1,column2", msg)

    def test_build_multimodal_request_content_text_only(self):
        f = MockUploadedFile("data.txt", b"hello", "text/plain")
        parsed = parse_uploaded_file(f)
        content = build_multimodal_request_content("안녕", [parsed])
        self.assertEqual(content, "안녕")

    def test_build_multimodal_request_content_with_image(self):
        img_mock = {
            "name": "photo.png",
            "is_image": True,
            "data_url": "data:image/png;base64,AAAA",
        }
        content = build_multimodal_request_content("사진 설명해줘", [img_mock])
        self.assertIsInstance(content, list)
        self.assertEqual(len(content), 2)
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")


if __name__ == "__main__":
    unittest.main()

