"""Page rendering and clean-up. The originals are stored untouched; this only prepares model input."""
from __future__ import annotations

import cv2
import fitz
import numpy as np

RENDER_DPI = 200
MAX_DESKEW_DEGREES = 15


def render_pdf_pages(pdf_bytes: bytes, dpi: int = RENDER_DPI) -> list[bytes]:
    """Original page images as JPEG, in page order."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return [p.get_pixmap(dpi=dpi, colorspace=fitz.csRGB).tobytes("jpeg", jpg_quality=85) for p in doc]


def page_count(pdf_bytes: bytes) -> int:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Password-protected PDFs are not supported")
        return doc.page_count


def estimate_skew(gray: np.ndarray) -> float:
    """Dominant text-line angle from a Hough transform on dark strokes, in degrees."""
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    joined = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3)))
    lines = cv2.HoughLinesP(joined, 1, np.pi / 720, threshold=200, minLineLength=gray.shape[1] // 4, maxLineGap=20)
    if lines is None:
        return 0.0
    angles = [np.degrees(np.arctan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4)]
    angles = [a for a in angles if abs(a) <= MAX_DESKEW_DEGREES]
    return float(np.median(angles)) if angles else 0.0


def rotate(img: np.ndarray, degrees: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def enhance(image_bytes: bytes, quarter_turns: int = 0) -> bytes:
    """Deskew and even out lighting while keeping colour, since pen colour can carry meaning."""
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Page image could not be decoded")
    if quarter_turns % 4:
        img = np.rot90(img, k=-(quarter_turns % 4)).copy()
    angle = estimate_skew(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    if 0.3 < abs(angle) <= MAX_DESKEW_DEGREES:
        img = rotate(img, angle)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    out = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise ValueError("Page image could not be encoded")
    return buf.tobytes()
