import re
from typing import Any
from html import escape


class SanitizationError(Exception):
    """Raised when input fails sanitization."""
    pass


class InputSanitizer:
    """Security-focused input sanitization (XSS, SQL injection, etc.)."""
    
    # Dangerous patterns
    HTML_PATTERN = re.compile(r'<[^>]+>')
    SCRIPT_PATTERN = re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL)
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"(--|;|\/\*|\*\/)",
        r"(\bOR\b.*\b=\b|\bAND\b.*\b=\b)",
    ]
    
    # Email pattern (RFC 5322 simplified)
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    
    # Phone pattern (international support)
    PHONE_PATTERN = re.compile(r'^\+?[\d\s\-\(\)]{7,20}$')
    
    @classmethod
    def sanitize_string(cls, value: str, max_length: int = 1000) -> str:
        """Sanitize a string input (strip HTML, trim, escape, enforce max length)."""
        if not isinstance(value, str):
            return str(value)
        
        # Remove null bytes
        value = value.replace('\x00', '')
        
        # Trim whitespace
        value = value.strip()
        
        # Remove HTML tags
        value = cls.HTML_PATTERN.sub('', value)
        
        # Remove script tags
        value = cls.SCRIPT_PATTERN.sub('', value)
        
        # Escape HTML entities
        value = escape(value, quote=True)
        
        # Remove control characters
        value = ''.join(char for char in value if ord(char) >= 32 or char in '\n\r\t')
        
        # Enforce max length
        if len(value) > max_length:
            value = value[:max_length]
        
        return value
    
    @classmethod
    def validate_email(cls, email: str) -> bool:
        """Validate email format."""
        if not email:
            return False
        return bool(cls.EMAIL_PATTERN.match(email.strip()))
    
    @classmethod
    def validate_phone(cls, phone: str) -> bool:
        """Validate phone number format."""
        if not phone:
            return False
        return bool(cls.PHONE_PATTERN.match(phone.strip()))
    
    @classmethod
    def sanitize_clinical_notes(cls, notes: str, max_length: int = 10000) -> str:
        """Sanitize clinical notes, allowing medical characters but preventing injection."""
        if not isinstance(notes, str):
            return str(notes)
        
        # Remove null bytes
        notes = notes.replace('\x00', '')
        
        # Trim whitespace
        notes = notes.strip()
        
        # Remove script tags only (keep medical symbols)
        notes = cls.SCRIPT_PATTERN.sub('', notes)
        
        # Allow alphanumeric, punctuation, and medical characters (preserves ICD/CPT codes).
        allowed_pattern = re.compile(r'[^a-zA-Z0-9\s\-.,;:\'\"()+\/\\[\]{}|@#$%^&=<>!?`~\d:.%-]')
        notes = allowed_pattern.sub('', notes)
        
        # Enforce max length
        if len(notes) > max_length:
            notes = notes[:max_length]
        
        return notes
    
    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """Sanitize uploaded filename (prevents path traversal and dangerous chars)."""
        if not filename:
            return "unnamed"
        
        # Remove path separators
        filename = filename.replace('/', '').replace('\\', '')
        
        # Get just the filename
        filename = filename.split('\\')[-1].split('/')[-1]
        
        # Remove dangerous characters
        dangerous_chars = r'[<>:"|?*\x00-\x1f]'
        filename = re.sub(dangerous_chars, '', filename)
        
        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name[:255-len(ext)-1] + '.' + ext if ext else name[:255]
        
        return filename or "unnamed"
    
    @classmethod
    def check_sql_injection(cls, value: str) -> bool:
        """Check if value contains SQL injection patterns (True if suspicious)."""
        if not isinstance(value, str):
            return False
        
        value_upper = value.upper()
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value_upper, re.IGNORECASE):
                return True
        
        return False
    
    @classmethod
    def sanitize_dict(cls, data: dict, max_length: int = 1000) -> dict:
        """Recursively sanitize a dictionary."""
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = cls.sanitize_string(str(value), max_length)
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_dict(value, max_length)
            elif isinstance(value, list):
                sanitized[key] = [
                    cls.sanitize_string(str(element), max_length) if isinstance(element, str) else element
                    for element in value
                ]
            else:
                sanitized[key] = value
        return sanitized


def sanitize_response(data: Any) -> Any:
    """Sanitize API response data to prevent XSS."""
    if isinstance(data, str):
        return escape(data)
    elif isinstance(data, dict):
        return {key: sanitize_response(value) for key, value in data.items()}
    elif isinstance(data, (list, tuple)):
        return [sanitize_response(item) for item in data]
    return data
