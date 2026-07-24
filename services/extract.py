"""근거자료 파일 → 평문 텍스트 추출 (대본 생성 입력용).

PDF(pypdf) + 평문(txt/md/csv) 지원. 장별 PDF 를 드래그드랍하면 본문을 뽑아
대본 생성의 근거(context)로 넣는다.
"""
from __future__ import annotations

import io

TEXT_EXTS = (".txt", ".md", ".markdown", ".csv", ".text")


def extract_text(data: bytes, filename: str) -> str:
    """파일 바이트에서 텍스트 추출. 지원 안 하는 형식이면 ValueError."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _extract_pdf(data)
    if name.endswith(TEXT_EXTS):
        for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode("utf-8", "replace")
    raise ValueError(f"지원하지 않는 형식입니다: {filename} (PDF 또는 txt/md 만 가능)")


def _extract_pdf(data: bytes) -> str:
    try:
        import pypdf
    except Exception as exc:  # pragma: no cover
        raise ValueError("pypdf 가 설치되지 않았습니다. setup.bat 을 다시 실행하세요.") from exc
    reader = pypdf.PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            parts.append(t.strip())
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError("PDF 에서 텍스트를 찾지 못했습니다(스캔 이미지 PDF일 수 있음).")
    return text
