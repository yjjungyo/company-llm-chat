"""첨부 파일 파싱 및 텍스트/이미지 추출 모듈.

지원 포맷:
- 문서: PDF (.pdf), Word (.docx), Excel (.xlsx, .xls), CSV (.csv)
- 텍스트/코드: TXT, MD, PY, JSON, YAML, XML, SQL, HTML, CSS, JS, TS, LOG 등
- 이미지: PNG, JPG, JPEG, WEBP, GIF (Base64 인코딩 및 리사이징)
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any


MAX_TEXT_CHARS_PER_FILE = 40_000  # 파일당 최대 추출 글자 수 (컨텍스트 윈도우 보호)


def format_file_size(size_bytes: int) -> str:
    """바이트 크기를 읽기 쉬운 단위로 변환."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """PDF 파일에서 텍스트 추출."""
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages_text: list[str] = []
        for idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                pages_text.append(f"--- [페이지 {idx + 1}] ---\n{text}")
        if not pages_text:
            return "(PDF에서 추출할 수 있는 텍스트가 없습니다. 스캔 이미지 기반 문서일 수 있습니다.)"
        return "\n\n".join(pages_text)
    except Exception as exc:
        return f"(PDF 파싱 실패: {exc})"


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Word (.docx) 파일에서 텍스트 추출."""
    try:
        import docx

        doc = docx.Document(io.BytesIO(file_bytes))
        lines: list[str] = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                lines.append(text)

        # 표(Table) 내용 추출
        for table_idx, table in enumerate(doc.tables):
            lines.append(f"\n[표 {table_idx + 1}]")
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    lines.append(" | ".join(cells))

        if not lines:
            return "(DOCX 파일에 텍스트 내용이 없습니다.)"
        return "\n".join(lines)
    except Exception as exc:
        return f"(DOCX 파싱 실패: {exc})"


def extract_text_from_excel(file_bytes: bytes, filename: str) -> str:
    """Excel (.xlsx, .xls) 파일에서 텍스트 추출."""
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheets_out: list[str] = []

        for sheet_name in wb.sheetnames[:5]:  # 최대 5개 시트
            ws = wb[sheet_name]
            sheet_lines: list[str] = []
            for row in ws.iter_rows(values_only=True):
                non_empty = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if non_empty:
                    sheet_lines.append(" | ".join(non_empty))
                if len(sheet_lines) >= 80:  # 시트당 최대 80행
                    sheet_lines.append("... (이하 행 생략) ...")
                    break

            if sheet_lines:
                sheets_out.append(f"### [시트: {sheet_name}]\n" + "\n".join(sheet_lines))

        if not sheets_out:
            return "(Excel 파일에 텍스트 데이터가 없습니다.)"
        return "\n\n".join(sheets_out)
    except Exception as exc:
        return f"(Excel 파싱 실패: {exc})"


def extract_text_from_plain_text(file_bytes: bytes) -> str:
    """일반 텍스트/코드/CSV 파일 디코딩."""
    for enc in ("utf-8", "cp949", "euc-kr", "utf-16", "latin-1"):
        try:
            return file_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return file_bytes.decode("utf-8", errors="replace")


def process_image(file_bytes: bytes, mime_type: str = "image/png") -> tuple[str, str]:
    """이미지를 리사이징 및 최적화하여 (data_url, base64_str) 반환."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(file_bytes))
        # 멀티모달 토큰 및 용량 절약을 위해 최대 1568x1568 리사이즈
        img.thumbnail((1568, 1568))

        buffered = io.BytesIO()
        # 투명도가 있거나 PNG면 PNG, 아니면 JPEG 변환
        if img.mode in ("RGBA", "P") or "png" in mime_type.lower():
            out_format = "PNG"
            out_mime = "image/png"
            img.save(buffered, format=out_format, optimize=True)
        else:
            out_format = "JPEG"
            out_mime = "image/jpeg"
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(buffered, format=out_format, quality=85)

        b64_str = base64.b64encode(buffered.getvalue()).decode("ascii")
        data_url = f"data:{out_mime};base64,{b64_str}"
        return data_url, b64_str
    except Exception:
        b64_str = base64.b64encode(file_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{b64_str}"
        return data_url, b64_str


def parse_uploaded_file(file_obj: Any) -> dict[str, Any]:
    """업로드된 Streamlit UploadedFile 객체를 파싱하여 메타데이터와 내용 추출."""
    name: str = getattr(file_obj, "name", "uploaded_file")
    size: int = getattr(file_obj, "size", 0)
    mime_type: str = getattr(file_obj, "type", "") or "application/octet-stream"

    # 파일 바이트 읽기
    file_bytes = file_obj.getvalue() if hasattr(file_obj, "getvalue") else file_obj.read()
    if not size:
        size = len(file_bytes)

    ext = Path(name).suffix.lower()

    is_image = ext in (".png", ".jpg", ".jpeg", ".webp", ".gif") or mime_type.startswith("image/")
    extracted_text = ""
    data_url = ""

    if is_image:
        data_url, _ = process_image(file_bytes, mime_type)
        extracted_text = f"(이미지 파일: {name})"
    elif ext == ".pdf":
        extracted_text = extract_text_from_pdf(file_bytes)
    elif ext in (".docx", ".doc"):
        extracted_text = extract_text_from_docx(file_bytes)
    elif ext in (".xlsx", ".xls"):
        extracted_text = extract_text_from_excel(file_bytes, name)
    else:
        # 코드, 마크다운, CSV, 텍스트 등
        extracted_text = extract_text_from_plain_text(file_bytes)

    # 글자 수 제한 적용
    if len(extracted_text) > MAX_TEXT_CHARS_PER_FILE:
        extracted_text = (
            extracted_text[:MAX_TEXT_CHARS_PER_FILE]
            + f"\n\n... (총 {len(extracted_text):,}자 중 앞부분 {MAX_TEXT_CHARS_PER_FILE:,}자만 추출됨) ..."
        )

    return {
        "name": name,
        "size": size,
        "size_str": format_file_size(size),
        "ext": ext,
        "is_image": is_image,
        "text": extracted_text,
        "data_url": data_url,
    }


def format_message_with_attachments(prompt_text: str, parsed_files: list[dict[str, Any]]) -> str:
    """사용자 메시지와 첨부 파일들을 DB 저장 및 화면 표시에 적합한 마크다운으로 포맷팅."""
    if not parsed_files:
        return prompt_text.strip()

    blocks: list[str] = []

    # 1. 상단 첨부 파일 목록 요약
    file_badges: list[str] = []
    for f in parsed_files:
        icon = "🖼️" if f["is_image"] else "📄"
        file_badges.append(f"- {icon} `{f['name']}` ({f['size_str']})")

    summary_block = f"📎 **첨부 파일 ({len(parsed_files)}개):**\n" + "\n".join(file_badges)
    blocks.append(summary_block)

    # 2. 사용자 질문 텍스트
    clean_prompt = prompt_text.strip() if prompt_text else "첨부된 파일의 내용을 분석하고 설명해줘."
    blocks.append(clean_prompt)

    # 3. 이미지 미리보기 (인라인 렌더링)
    for f in parsed_files:
        if f["is_image"] and f["data_url"]:
            blocks.append(f"![{f['name']}]({f['data_url']})")

    # 4. 텍스트/문서 파일 내용 접이식 세부정보 (<details>)
    for f in parsed_files:
        if not f["is_image"] and f["text"]:
            code_lang = f["ext"].lstrip(".") if f["ext"] else "text"
            if code_lang in ("pdf", "docx", "xlsx", "xls"):
                code_lang = "markdown"

            detail_block = (
                f"<details>\n"
                f"<summary>📄 <b>[{f['name']}] 내용 펼치기</b> ({len(f['text']):,}자)</summary>\n\n"
                f"```{code_lang}\n"
                f"{f['text']}\n"
                f"```\n"
                f"</details>"
            )
            blocks.append(detail_block)

    return "\n\n".join(blocks)


def build_multimodal_request_content(message_content: str, parsed_files: list[dict[str, Any]]) -> str | list[dict[str, Any]]:
    """LLM API에 전달할 메시지 content 생성.

    이미지가 포함되어 있으면 OpenAI Vision 형식(list[dict]),
    그렇지 않으면 텍스트 문자열(str)을 반환합니다.
    """
    image_files = [f for f in parsed_files if f.get("is_image") and f.get("data_url")]
    if not image_files:
        return message_content

    # OpenAI Vision 규격
    content_list: list[dict[str, Any]] = [
        {"type": "text", "text": message_content}
    ]
    for img in image_files:
        content_list.append({
            "type": "image_url",
            "image_url": {
                "url": img["data_url"],
                "detail": "auto",
            },
        })

    return content_list

