import json
import logging
from typing import List, Dict, Optional

from openai import AsyncOpenAI
from celery import shared_task

from app.core.logging import integration_logger
from app.core.config import settings

logger = logging.getLogger("healthpa.ai")


class ClinicalCodeExtractor:
    """Extracts ICD-10 and CPT codes from clinical notes using the Groq API."""
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
        self.model = "llama-3.1-8b-instant"
    
    async def extract_codes(self, clinical_notes: str) -> Dict:
        """Extract ICD-10 and CPT codes from clinical notes."""
        if not settings.GROQ_API_KEY:
            integration_logger.error("Groq API key missing in configuration.")
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
                response_format={ "type": "json_object" },
                temperature=0
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
        """Analyze a PA request for completeness using AI."""
        if not settings.GROQ_API_KEY:
            return {"error": "AI provider not configured"}
        
        prompt = f"Analyze this PA Request for clinical necessity:\n{json.dumps(pa_data)}"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            return {"analysis": response.choices[0].message.content, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}


@shared_task
def extract_codes_task(clinical_notes: str) -> Dict:
    """Celery task wrapper for background AI processing."""
    import asyncio
    
    extractor = ClinicalCodeExtractor()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(extractor.extract_codes(clinical_notes))
    finally:
        loop.close()
    
    return result