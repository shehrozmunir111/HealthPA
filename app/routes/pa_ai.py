"""AI grounded-coding endpoints (JWT + hospital_id scoped).

POST /api/v1/pa/{id}/extract        -> RAG+rerank+grounded extract; pause for review
GET  /api/v1/pa/{id}/proposed-codes -> proposed codes + citations (from checkpoint)
POST /api/v1/pa/{id}/review         -> resume graph; finalize codes
POST /api/v1/pa/{id}/ask            -> coder policy-QA (ReAct/RAG)
POST /api/v1/policies/reindex       -> rebuild the hospital's persistent index

Every endpoint is tenant-scoped (the PA must belong to the caller's hospital;
retrieval/memory are namespaced by hospital_id). The synchronous AI services run
in a threadpool. AI events are audit-logged ("ai_codes_proposed",
"codes_reviewed" with before/after).
"""

import json
import logging
import os
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import CurrentUser, DbSession, HospitalCtx
from app.models.audit_log import AuditAction
from app.models.pa_request import FSMTransitionError, PARequest, PARequestStatus
from app.schemas.codes import AskRequest, ReindexRequest, ReviewDecision
from app.services.audit_service import AuditService
from app.services.code_extraction_graph import code_extraction_graph
from app.services.coding_agent import coding_agent
from app.services.llm_provider import get_chat_model_safe
from app.services.long_term_memory import long_term_memory
from app.services.rag_service import rag_service

logger = logging.getLogger("healthpa.ai.routes")

router = APIRouter()


async def _get_pa(db, hospital_ctx, pa_id: UUID) -> PARequest:
    """Load a PA case scoped to the caller's hospital (404 otherwise)."""
    res = await db.execute(
        select(PARequest).where(
            PARequest.id == pa_id,
            PARequest.hospital_id == hospital_ctx.hospital_id,
        )
    )
    pa = res.scalar_one_or_none()
    if pa is None:
        raise HTTPException(status_code=404, detail="PA request not found")
    return pa


@router.post("/pa/{pa_id}/extract")
async def extract_codes(
    pa_id: UUID, db: DbSession, user: CurrentUser, hospital_ctx: HospitalCtx
):
    pa = await _get_pa(db, hospital_ctx, pa_id)

    try:
        result = await run_in_threadpool(
            code_extraction_graph.start,
            hospital_id=hospital_ctx.hospital_id,
            pa_id=pa.id,
            clinical_notes=pa.clinical_notes or "",
            payer=pa.payer_name,
        )
    except Exception as exc:
        logger.warning("AI extraction failed (%s); using rule-based fallback", exc)
        from app.services.grounded_extractor import rule_based_extract
        fallback = rule_based_extract(pa.clinical_notes or "")
        result = {
            "status": "pending_review",
            "proposed": fallback.model_dump(),
            "summary": "Rule-based extraction (AI pipeline unavailable).",
        }

    await AuditService.log_action(
        db=db,
        hospital_id=hospital_ctx.hospital_id,
        user_id=user.id,
        user_email=user.email,
        action=AuditAction.AI_CODES_PROPOSED,
        resource_type="pa_request",
        resource_id=pa.id,
        description="AI proposed codes for review",
        details={"status": result.get("status"), "proposed": result.get("proposed")},
        tags=["ai", "coding"],
    )
    return result


@router.get("/pa/{pa_id}/proposed-codes")
async def proposed_codes(
    pa_id: UUID, db: DbSession, user: CurrentUser, hospital_ctx: HospitalCtx
):
    pa = await _get_pa(db, hospital_ctx, pa_id)
    return await run_in_threadpool(code_extraction_graph.get_proposed, pa_id=pa.id)


@router.post("/pa/{pa_id}/review")
async def review_codes(
    pa_id: UUID,
    body: ReviewDecision,
    db: DbSession,
    user: CurrentUser,
    hospital_ctx: HospitalCtx,
):
    pa = await _get_pa(db, hospital_ctx, pa_id)
    before = {
        "diagnosis_codes": list(pa.diagnosis_codes or []),
        "procedure_codes": list(pa.procedure_codes or []),
    }

    result = await run_in_threadpool(
        code_extraction_graph.resume, pa_id=pa.id, decision=body.model_dump()
    )
    final = result.get("final_codes", [])

    if body.decision in ("approve", "edit"):
        # The reviewed set is authoritative — assign unconditionally so an edit
        # that *removes* codes actually clears the column (don't keep stale codes).
        pa.diagnosis_codes = [
            code.get("code") for code in final if code.get("code_system") == "ICD10"
        ]
        pa.procedure_codes = [
            code.get("code") for code in final if code.get("code_system") == "CPT"
        ]
        # Advance the PA's workflow status so the case leaves the review queue.
        # Guarded by the FSM — only legal from PENDING; other states keep status.
        try:
            pa.transition_to(
                PARequestStatus.APPROVED,
                user_id=str(user.id),
                notes="AI-proposed codes approved by reviewer",
            )
        except FSMTransitionError:
            logger.info(
                "PA %s in status %s cannot move to APPROVED; codes saved, status kept",
                pa.id,
                pa.status,
            )
    pa.ai_extracted_codes = {
        "final_codes": final,
        "decision": body.decision,
        "reviewed_by": str(user.id),
        "status": result.get("status"),
    }
    db.add(pa)

    after = {
        "diagnosis_codes": list(pa.diagnosis_codes or []),
        "procedure_codes": list(pa.procedure_codes or []),
    }
    await AuditService.log_action(
        db=db,
        hospital_id=hospital_ctx.hospital_id,
        user_id=user.id,
        user_email=user.email,
        action=AuditAction.CODES_REVIEWED,
        resource_type="pa_request",
        resource_id=pa.id,
        description=f"Codes reviewed: {body.decision}",
        details={"decision": body.decision, "before": before, "after": after},
        tags=["ai", "coding", "review"],
    )

    # Learn recurring corrections per coder/hospital (any reviewer edit).
    if body.decision == "edit":
        await run_in_threadpool(
            long_term_memory.add_correction,
            hospital_ctx.hospital_id,
            user.id,
            before=before,
            after=after,
            note=body.reviewer_notes,
        )

    return {
        "status": result.get("status"),
        "final_codes": final,
        "decision": body.decision,
        "pa_status": pa.status.value,
    }


@router.post("/pa/{pa_id}/ask")
async def ask(
    pa_id: UUID,
    body: AskRequest,
    db: DbSession,
    user: CurrentUser,
    hospital_ctx: HospitalCtx,
):
    pa = await _get_pa(db, hospital_ctx, pa_id)
    conversation_id = body.conversation_id or f"ask-{pa.id}"

    pa_summary = (
        f"PA {pa.request_number}: status={pa.status.value}; payer={pa.payer_name}; "
        f"notes={pa.clinical_notes or ''}"
    )
    codes_summary = json.dumps(pa.ai_extracted_codes or {})
    llm = get_chat_model_safe()

    return await run_in_threadpool(
        coding_agent.run,
        hospital_ctx.hospital_id,
        body.message,
        conversation_id,
        llm=llm,
        pa_lookup=lambda _pid: pa_summary,
        codes_lookup=lambda _pid: codes_summary,
    )


@router.post("/policies/reindex")
async def reindex_policies(
    body: ReindexRequest, db: DbSession, user: CurrentUser, hospital_ctx: HospitalCtx
):
    """Rebuild the hospital's persistent policy index from its docs directory.

    Cached (no re-embed) unless the corpus changed or ``force`` is set.
    """
    corpus_dir = os.path.join(settings.POLICY_DOCS_DIR, str(hospital_ctx.hospital_id))
    items = []
    if os.path.isdir(corpus_dir):
        for name in sorted(os.listdir(corpus_dir)):
            path = os.path.join(corpus_dir, name)
            if os.path.isfile(path):
                items.append({"path": path, "source_doc": name})

    result = await run_in_threadpool(
        rag_service.ingest_paths, hospital_ctx.hospital_id, items, force=body.force
    )
    return result
