"""
OCR Service for extracting text from medical documents
Supports both images and PDFs using PyTesseract and pdf2image
"""

import os
import uuid
import logging
from pathlib import Path
from typing import Optional, List
from tempfile import TemporaryDirectory

from PIL import Image
from celery import shared_task

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

from app.core.config import settings

logger = logging.getLogger("healthpa.ocr")


def _get_pytesseract():
    """Import pytesseract lazily so the app can boot without OCR extras."""
    try:
        import pytesseract
    except ImportError as exc:
        raise ImportError(
            "pytesseract is required for OCR processing. Install the OCR dependencies first."
        ) from exc

    return pytesseract


@shared_task(bind=True, max_retries=3)
def process_ocr(self, file_path: str, file_name: str) -> dict:
    """
    Celery task to process OCR on uploaded documents.
    Supports images (PNG, JPG, TIFF, BMP) and PDFs.
    
    Args:
        file_path: Path to the uploaded file
        file_name: Original file name
        
    Returns:
        dict with extracted_text, confidence, and metadata
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_ext = Path(file_name).suffix.lower()
        
        if file_ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
            result = _process_image(file_path)
            
        elif file_ext == '.pdf':
            result = _process_pdf(file_path)
            
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
        
        return {
            "success": True,
            "file_name": file_name,
            "extracted_text": result["text"],
            "confidence_score": result["confidence"],
            "word_count": len(result["text"].split()),
            "file_path": file_path,
            "pages_processed": result.get("pages_processed", 1)
        }
        
    except Exception as exc:
        logger.error(f"OCR processing failed for {file_name}: {str(exc)}")
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        return {
            "success": False,
            "error": str(exc),
            "file_name": file_name
        }


def _process_image(image_path: str) -> dict:
    """Process a single image file with OCR."""
    pytesseract = _get_pytesseract()
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image)
    
    conf_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    conf_values = [int(c) for c in conf_data['conf'] if int(c) > 0]
    avg_confidence = sum(conf_values) / len(conf_values) if conf_values else 0
    
    return {
        "text": text,
        "confidence": round(avg_confidence, 2),
        "pages_processed": 1
    }


def _process_pdf(pdf_path: str) -> dict:
    """
    Process a PDF file by converting each page to an image and applying OCR.
    """
    pytesseract = _get_pytesseract()
    if not PDF2IMAGE_AVAILABLE:
        raise ImportError(
            "pdf2image library is required for PDF processing. "
            "Install with: pip install pdf2image"
        )
    
    try:
        images = convert_from_path(pdf_path, dpi=300)
    except Exception as e:
        raise RuntimeError(f"Failed to convert PDF to images: {str(e)}")
    
    all_text_parts = []
    all_confidences = []
    
    for page_num, image in enumerate(images, 1):
        page_text = pytesseract.image_to_string(image)
        all_text_parts.append(f"--- Page {page_num} ---\n{page_text}")
        
        conf_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        conf_values = [int(c) for c in conf_data['conf'] if int(c) > 0]
        if conf_values:
            all_confidences.extend(conf_values)
    
    combined_text = "\n\n".join(all_text_parts)
    avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0
    
    logger.info(f"PDF processed: {len(images)} pages, {len(combined_text.split())} words")
    
    return {
        "text": combined_text,
        "confidence": round(avg_confidence, 2),
        "pages_processed": len(images)
    }


def save_upload_file(upload_file) -> str:
    """
    Save uploaded file to disk and return path.
    
    Args:
        upload_file: FastAPI UploadFile object
        
    Returns:
        str: Path to saved file
    """
    file_ext = Path(upload_file.filename).suffix
    unique_name = f"{uuid.uuid4()}{file_ext}"
    
    upload_dir = Path(settings.OCR_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / unique_name
    
    with open(file_path, "wb") as buffer:
        buffer.write(upload_file.file.read())
    
    return str(file_path)
