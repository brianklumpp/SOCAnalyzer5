"""
GRaCe (Governance, Risk & Compliance Assistant) API Router

Endpoints for conversational AI assistance on SOC reports.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import logging

from ..database import get_db
from ..services import grace_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/grace", tags=["GRaCe Assistant"])


class ConversationMessage(BaseModel):
    """A single message in conversation history."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class AskGraceRequest(BaseModel):
    """Request to ask GRaCe a question."""
    message: str = Field(..., description="User's question or request", min_length=1, max_length=2000)
    conversation_history: List[ConversationMessage] = Field(default_factory=list, description="Previous conversation messages")
    include_full_context: bool = Field(False, description="Include full scan data in context (slower, more accurate)")


class AskGraceResponse(BaseModel):
    """GRaCe's response."""
    response: str = Field(..., description="GRaCe's answer")
    conversation_length: int = Field(0, description="Number of messages in conversation history")
    context_included: bool = Field(False, description="Whether full context was included")
    error: Optional[str] = Field(None, description="Error message if applicable")


class ConversationHistory(BaseModel):
    """Conversation history for a scan."""
    scan_id: int
    messages: List[ConversationMessage]
    total_messages: int


@router.post("/{scan_id}/message", response_model=AskGraceResponse)
async def ask_grace(
    scan_id: int,
    request: AskGraceRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Ask GRaCe a question about a specific scan.
    
    Maintains conversation context within the session.
    Use clear endpoint to reset conversation.
    
    Examples:
    - "What controls have deviations?"
    - "Summarize the CUECs in this report"
    - "Which TSC criteria have weak coverage?"
    - "Tell me more about control DS-1"
    """
    try:
        result = await grace_service.ask_grace(
            db=db,
            scan_id=scan_id,
            user_message=request.message,
            include_full_context=request.include_full_context
        )
        
        return AskGraceResponse(**result)
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error in ask_grace endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{scan_id}/history", response_model=ConversationHistory)
async def get_conversation_history(scan_id: int):
    """
    Get conversation history for a scan.
    
    Returns the last N messages (both user and assistant).
    """
    history = grace_service.get_conversation_history(scan_id)
    
    return ConversationHistory(
        scan_id=scan_id,
        messages=[ConversationMessage(**msg) for msg in history],
        total_messages=len(history)
    )


@router.delete("/{scan_id}/conversation")
async def clear_conversation(scan_id: int):
    """
    Clear conversation history for a scan.
    
    Use this to start a fresh conversation or reset context.
    """
    grace_service.clear_conversation(scan_id)
    
    return {
        "status": "ok",
        "message": f"Conversation cleared for scan {scan_id}"
    }


@router.get("/{scan_id}/context")
async def get_scan_context_endpoint(scan_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get the scan context that GRaCe uses for answers.
    
    Useful for debugging or understanding what data GRaCe has access to.
    """
    try:
        context = await grace_service.get_scan_context(db, scan_id)
        summary = grace_service.build_context_summary(context)
        
        return {
            "scan_id": scan_id,
            "summary": summary,
            "stats": {
                "total_controls": context['total_controls'],
                "controls_with_deviations": context['controls_with_deviations'],
                "total_cuecs": context['total_cuecs'],
                "high_confidence_cuecs": context['high_confidence_cuecs'],
                "low_confidence_cuecs": context['low_confidence_cuecs'],
                "total_subservice_orgs": context['total_subservice_orgs'],
                "detected_standards": context['detected_standards'],
                "active_frameworks": context['active_frameworks']
            }
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting scan context: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
