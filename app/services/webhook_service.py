"""
Webhook Service for HealthPA
Sends notifications to external systems on PA status changes
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from uuid import UUID
import asyncio
from threading import Thread

import httpx

from app.core.config import settings
from app.models.pa_request import PARequestStatus

logger = logging.getLogger("healthpa.webhook")


class WebhookEvent:
    """Webhook event types."""
    PA_CREATED = "pa_request.created"
    PA_STATUS_CHANGED = "pa_request.status_changed"
    PA_APPROVED = "pa_request.approved"
    PA_DENIED = "pa_request.denied"
    PA_NEEDS_INFO = "pa_request.needs_info"
    PA_COMPLETED = "pa_request.completed"


class WebhookPayload:
    """Standard webhook payload structure."""
    
    def __init__(
        self,
        event: str,
        pa_request_id: UUID,
        hospital_id: UUID,
        status: str,
        request_number: str,
        patient_id: Optional[UUID] = None,
        decision_notes: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        self.event = event
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.data = {
            "pa_request_id": str(pa_request_id),
            "hospital_id": str(hospital_id),
            "status": status,
            "request_number": request_number,
            "patient_id": str(patient_id) if patient_id else None,
            "decision_notes": decision_notes,
            "metadata": metadata or {}
        }
    
    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "timestamp": self.timestamp,
            "data": self.data
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class WebhookService:
    """
    Service for sending webhook notifications.
    Supports async delivery with retry logic.
    """
    
    def __init__(self):
        self.webhook_urls: List[str] = self._get_webhook_urls()
        self.timeout = 30
        self.max_retries = 3
    
    def _get_webhook_urls(self) -> List[str]:
        """Get configured webhook URLs from settings."""
        if hasattr(settings, 'WEBHOOK_URLS') and settings.WEBHOOK_URLS:
            return [url.strip() for url in settings.WEBHOOK_URLS.split(',') if url.strip()]
        return []
    
    def is_enabled(self) -> bool:
        """Check if webhooks are configured."""
        return len(self.webhook_urls) > 0
    
    def send_async(self, payload: WebhookPayload) -> None:
        """
        Send webhook asynchronously in a background thread.
        Does not block the main request.
        """
        if not self.is_enabled():
            return
        
        def _send():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._send_webhooks(payload))
            finally:
                loop.close()
        
        thread = Thread(target=_send, daemon=True)
        thread.start()
    
    async def _send_webhooks(self, payload: WebhookPayload) -> None:
        """Send webhook to all configured URLs."""
        tasks = [
            self._send_with_retry(url, payload)
            for url in self.webhook_urls
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_with_retry(self, url: str, payload: WebhookPayload) -> bool:
        """Send webhook with exponential backoff retry."""
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        url,
                        content=payload.to_json(),
                        headers={
                            "Content-Type": "application/json",
                            "X-HealthPA-Event": payload.event,
                            "X-HealthPA-Timestamp": payload.timestamp
                        }
                    )
                    
                    if response.status_code in (200, 201, 202, 204):
                        logger.info(
                            f"Webhook sent successfully to {url} "
                            f"(event: {payload.event}, status: {response.status_code})"
                        )
                        return True
                    else:
                        logger.warning(
                            f"Webhook returned non-success status {response.status_code} "
                            f"to {url}: {response.text[:200]}"
                        )
                        
            except httpx.TimeoutException:
                logger.warning(f"Webhook timeout to {url} (attempt {attempt + 1}/{self.max_retries})")
            except httpx.RequestError as e:
                logger.warning(f"Webhook request error to {url}: {str(e)} (attempt {attempt + 1}/{self.max_retries})")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        logger.error(f"Webhook failed after {self.max_retries} attempts to {url}")
        return False
    
    def notify_pa_created(
        self,
        pa_request_id: UUID,
        hospital_id: UUID,
        request_number: str,
        patient_id: Optional[UUID] = None
    ) -> None:
        """Notify that a new PA request was created."""
        payload = WebhookPayload(
            event=WebhookEvent.PA_CREATED,
            pa_request_id=pa_request_id,
            hospital_id=hospital_id,
            status="created",
            request_number=request_number,
            patient_id=patient_id
        )
        self.send_async(payload)
    
    def notify_status_changed(
        self,
        pa_request_id: UUID,
        hospital_id: UUID,
        status: PARequestStatus,
        request_number: str,
        patient_id: Optional[UUID] = None,
        decision_notes: Optional[str] = None
    ) -> None:
        """Notify that PA request status changed."""
        event_type = self._get_event_for_status(status)
        
        payload = WebhookPayload(
            event=event_type,
            pa_request_id=pa_request_id,
            hospital_id=hospital_id,
            status=status.value,
            request_number=request_number,
            patient_id=patient_id,
            decision_notes=decision_notes
        )
        self.send_async(payload)
    
    def _get_event_for_status(self, status: PARequestStatus) -> str:
        """Map PA status to webhook event type."""
        status_event_map = {
            PARequestStatus.APPROVED: WebhookEvent.PA_APPROVED,
            PARequestStatus.DENIED: WebhookEvent.PA_DENIED,
            PARequestStatus.NEEDS_INFO: WebhookEvent.PA_NEEDS_INFO,
            PARequestStatus.COMPLETED: WebhookEvent.PA_COMPLETED,
        }
        return status_event_map.get(status, WebhookEvent.PA_STATUS_CHANGED)


webhook_service = WebhookService()
