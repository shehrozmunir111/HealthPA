"""
AI Engine Service for clinical code extraction
Professional version using OpenRouter API (OpenAI-Compatible)
"""

import json
import logging
from typing import List, Dict, Optional

from openai import AsyncOpenAI
from celery import shared_task

from app.core.logging import integration_logger
from app.core.config import settings

logger = logging.getLogger("healthpa.ai")


class ClinicalCodeExtractor:
    """
    Extracts ICD-10 and CPT codes from clinical notes using OpenRouter.
    Standardized to work with any model (Claude, GPT, Llama).
    """
    
    def __init__(self):
        # OpenRouter uses OpenAI SDK with a custom base URL
        self.client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        # Professional Default Model (Can be swapped to any OpenRouter model)
        self.model = "anthropic/claude-3-sonnet:beta"
    
    async def extract_codes(self, clinical_notes: str) -> Dict:
        """
        Extract ICD-10 and CPT codes from clinical notes.
        
        Args:
            clinical_notes: Raw clinical text from OCR or uploads.
            
        Returns:
            Dict with extracted codes and confidence score.
        """
        if not settings.OPENROUTER_API_KEY:
            integration_logger.error("OpenRouter API key missing in configuration.")
            return {
                "icd10_codes": [],
                "cpt_codes": [],
                "confidence": 0.0,
                "error": "AI provider not configured"
            }
        
        prompt = f"""
        You are a medical coding expert. Extract all relevant ICD-10 diagnosis codes and CPT procedure codes 
        from the clinical notes provided. Return ONLY a valid JSON object.
        
        REQUIRED FORMAT:
        {{
            "icd10_codes": [
                {{"code": "CODE", "description": "TEXT"}}
            ],
            "cpt_codes": [
                {{"code": "CODE", "description": "TEXT"}}
            ],
            "confidence": 0.0 to 1.0
        }}
        
        Clinical Notes:
        ---
        {clinical_notes}
        ---
        """
        
        try:
            integration_logger.info(f"Initiating AI extraction with model: {self.model}")
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional medical coder."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" }, # Enforce JSON mode
                temperature=0,
                extra_headers={
                    "HTTP-Referer": "https://healthpa.ai", # Required by OpenRouter
                    "X-Title": "HealthPA Clinical Engine"
                }
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            return {
                "icd10_codes": result.get("icd10_codes", []),
                "cpt_codes": result.get("cpt_codes", []),
                "confidence": result.get("confidence", 0.0),
                "model_used": self.model
            }
            
        except Exception as e:
            integration_logger.error(f"AI Extraction Failure: {str(e)}")
            return {
                "icd10_codes": [],
                "cpt_codes": [],
                "confidence": 0.0,
                "error": str(e)
            }
    
    async def analyze_pa_request(self, pa_data: Dict) -> Dict:
        """
        Analyze a PA request for completeness using AI.
        """
        if not settings.OPENROUTER_API_KEY:
            return {"error": "AI provider not configured"}
        
        prompt = f"Analyze this PA Request for clinical necessity:\n{json.dumps(pa_data)}"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                extra_headers={
                    "HTTP-Referer": "https://healthpa.ai",
                    "X-Title": "HealthPA Clinical Engine"
                }
            )
            return {"analysis": response.choices[0].message.content, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}


@shared_task
def extract_codes_task(clinical_notes: str) -> Dict:
    """
    Celery task wrapper for background AI processing.
    """
    import asyncio
    
    extractor = ClinicalCodeExtractor()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(extractor.extract_codes(clinical_notes))
    finally:
        loop.close()
    
    return result