"""
OCR Engine Module (RapidOCR via ONNXRuntime)
============================================
Provides lightweight, local, dependency-contained optical character recognition (OCR)
for scanned and image-only PDF documents and standalone image assets.
"""

import logging
from pathlib import Path
from typing import Optional, Union, List, Dict, Any
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_ocr_engine_instance = None

def get_ocr_engine():
    """Lazy singleton accessor for the RapidOCR engine to prevent redundant ONNX model reloads."""
    global _ocr_engine_instance
    if _ocr_engine_instance is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine_instance = RapidOCR()
            logger.info("Initialized RapidOCR (ONNXRuntime) engine successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize RapidOCR engine: {e}")
            raise
    return _ocr_engine_instance

def clean_ocr_text(text: str) -> str:
    """
    Post-process OCR output to restore natural word spacing for English text.
    Handles fused words from ONNX OCR tokens (e.g. PascalCase, punctuation spacing, numbers).
    """
    if not text:
        return ""
    import re
    # Separate lowercase followed by uppercase: "EdgewaterBeach" -> "Edgewater Beach"
    t = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Punctuation spacing: "Ferrario,President" -> "Ferrario, President"
    t = re.sub(r'([,;:])([A-Za-z])', r'\1 \2', t)
    # Number spacing: "January28,2021" -> "January 28, 2021"
    t = re.sub(r'([A-Za-z])(\d)', r'\1 \2', t)
    t = re.sub(r',(\d)', r', \1', t)
    # Dot spacing: "MichaelE.Jackson" -> "Michael E. Jackson"
    t = re.sub(r'(\.)([A-Za-z])', r'\1 \2', t)
    return t


def ocr_image(image_input: Union[Image.Image, np.ndarray, str, Path]) -> str:
    """
    Perform optical character recognition on a PIL Image, NumPy array, or image file path.
    Returns extracted text lines joined by newlines with natural spacing.
    """
    if image_input is None:
        return ""

    try:
        if isinstance(image_input, (str, Path)):
            p = Path(image_input)
            if not p.exists():
                return ""
            img = Image.open(p).convert("RGB")
            img_arr = np.array(img)
        elif isinstance(image_input, Image.Image):
            img_arr = np.array(image_input.convert("RGB"))
        elif isinstance(image_input, np.ndarray):
            img_arr = image_input
        else:
            return ""

        engine = get_ocr_engine()
        result, _ = engine(img_arr)
        if not result:
            return ""

        # Extract text strings from bounding box results: [[box, text, score], ...]
        lines = [clean_ocr_text(item[1].strip()) for item in result if len(item) > 1 and item[1].strip()]
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Error during image OCR: {e}")
        return ""


def ocr_pdf_pages(pdf_path: Union[str, Path], max_pages: int = 10, scale: float = 1.5) -> str:
    """
    Render PDF pages to high-resolution images via pypdfium2 and extract text via OCR.
    Enforces C-level resource cleanup and bounds extraction to max_pages.
    """
    p = Path(pdf_path)
    if not p.exists():
        return ""

    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("pypdfium2 is not installed; cannot render PDF pages for OCR.")
        return ""

    ocr_pages: List[str] = []
    try:
        with pdfium.PdfDocument(p) as pdf:
            total_pages = len(pdf)
            pages_to_process = min(total_pages, max(1, max_pages))
            
            for page_idx in range(pages_to_process):
                page = pdf.get_page(page_idx)
                try:
                    # Render page at high resolution (scale=2.0 ~ 144 DPI)
                    pil_img = page.render(scale=scale).to_pil()
                    page_text = ocr_image(pil_img)
                    if page_text and page_text.strip():
                        ocr_pages.append(f"--- Page {page_idx + 1} ---\n{page_text.strip()}")
                finally:
                    page.close()

            if total_pages > pages_to_process:
                ocr_pages.append(f"[... Truncated: OCR processed first {pages_to_process} of {total_pages} pages ...]")
    except Exception as e:
        logger.warning(f"Error during PDF page OCR on {p}: {e}")
        return ""

    if ocr_pages:
        return "\n\n".join(ocr_pages)
    return ""

def ocr_document_core(file_path: Optional[Union[str, Path]], max_pages: int = 10) -> str:
    """
    Unified core extraction function: dispatches to PDF page OCR or image OCR based on file extension.
    """
    if not file_path:
        return ""
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return ""

    ext = p.suffix.lower()
    if ext == ".pdf":
        return ocr_pdf_pages(p, max_pages=max_pages)
    elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"]:
        return ocr_image(p)
    return ""

try:
    import pixeltable as pxt
    PIXELTABLE_AVAILABLE = True
except ImportError:
    pxt = None
    PIXELTABLE_AVAILABLE = False

if PIXELTABLE_AVAILABLE:
    @pxt.udf
    def pxt_ocr_document(
        file_path: Optional[pxt.String],
        max_pages: int = 10
    ) -> Optional[pxt.String]:
        """Declarative Pixeltable UDF: Extract text from scanned/image PDFs and images using RapidOCR."""
        if not file_path:
            return ""
        return ocr_document_core(file_path, max_pages=max_pages)

def attach_ocr_columns(
    domain: str,
    table_name: str,
    max_pages: int = 10,
    column_name: str = "ocr_text"
) -> Dict[str, Any]:
    """
    Declaratively attach an OCR computed column to a Pixeltable table.
    """
    if not PIXELTABLE_AVAILABLE:
        return {"status": "error", "message": "Pixeltable is not available."}

    from src.db.manager import DBManager
    full_table_path = DBManager.resolve_table_path(domain, table_name)
    try:
        tbl = pxt.get_table(full_table_path)
    except Exception as e:
        return {"status": "error", "message": f"Table '{full_table_path}' not found: {e}"}

    cols = list(tbl.columns()) if callable(tbl.columns) else list(tbl._schema.keys())

    # Determine source column
    target_col = None
    if "file_path" in cols:
        target_col = tbl.file_path
    elif "doc" in cols:
        target_col = tbl.doc
    elif "image" in cols:
        target_col = tbl.image
    else:
        return {"status": "error", "message": f"Table '{full_table_path}' lacks 'file_path', 'doc', or 'image' columns."}

    columns_added = []
    if column_name not in cols:
        tbl.add_computed_column(
            **{column_name: pxt_ocr_document(target_col, max_pages=max_pages)},
            if_exists="ignore"
        )
        columns_added.append(column_name)
        DBManager.record_operation(domain, table_name, {"action": "single_column", "column": column_name})

    return {
        "status": "success",
        "message": f"Successfully attached OCR column '{column_name}' to `{full_table_path}`.",
        "columns": columns_added or [column_name],
        "table": full_table_path
    }
