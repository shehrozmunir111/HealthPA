"""
OCR Service for extracting text from medical documents
Uses local PyTesseract (no external API costs)
"""

import os
import uuid
from pathlib import Path
from typing import Optional

import pytesseract
from PIL import Image
from celery import shared_task

from app.core.config import settings


@shared_task(bind=True, max_retries=3)
def process_ocr(self, file_path: str, file_name: str) -> dict:
    """
    Celery task to process OCR on uploaded documents.
    
    Args:
        file_path: Path to the uploaded file
        file_name: Original file name
        
    Returns:
        dict with extracted_text, confidence, and metadata
    """
    try:
        # Validate file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Process based on file type
        file_ext = Path(file_name).suffix.lower()
        
        if file_ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
            # Process image
            image = Image.open(file_path)
            extracted_text = pytesseract.image_to_string(image)
            confidence = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            # Calculate average confidence
            conf_values = [int(c) for c in confidence['conf'] if int(c) > 0]
            avg_confidence = sum(conf_values) / len(conf_values) if conf_values else 0
            
        elif file_ext == '.pdf':
            # For PDFs, you'd typically convert to images first
            # This is a simplified version
            extracted_text = "PDF processing requires pdf2image library"
            avg_confidence = 0
            
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")
        
        return {
            "success": True,
            "file_name": file_name,
            "extracted_text": extracted_text,
            "confidence_score": round(avg_confidence, 2),
            "word_count": len(extracted_text.split()),
            "file_path": file_path
        }
        
    except Exception as exc:
        # Retry with exponential backoff
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        return {
            "success": False,
            "error": str(exc),
            "file_name": file_name
        }


def save_upload_file(upload_file) -> str:
    """
    Save uploaded file to disk and return path.
    
    Args:
        upload_file: FastAPI UploadFile object
        
    Returns:
        str: Path to saved file
    """
    # Create unique filename
    file_ext = Path(upload_file.filename).suffix
    unique_name = f"{uuid.uuid4()}{file_ext}"
    
    # Ensure upload directory exists
    upload_dir = Path(settings.OCR_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / unique_name
    
    # Save file
    with open(file_path, "wb") as buffer:
        buffer.write(upload_file.file.read())
    
    return str(file_path)