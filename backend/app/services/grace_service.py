"""
GRaCe (Governance, Risk & Compliance Assistant) Service

Provides conversational AI assistance for SOC report analysis.
Maintains short-term conversation memory per scan session.
"""

import logging
import os
import json
from typing import List, Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from ..models import Scan, Control, CUEC, SubserviceOrg, Company, Product
from ..gpt_client import gpt_extract

logger = logging.getLogger(__name__)

# In-memory conversation storage (per scan_id)
# In production, could move to Redis for scaling
_conversation_sessions: Dict[int, List[Dict[str, str]]] = {}

MAX_HISTORY_MESSAGES = 10  # Keep last N messages for context

GRACE_SYSTEM_PROMPT = """You are GRaCe (Governance, Risk & Compliance Assistant), an expert AI assistant for SOC 2 and SOC 1 audit report analysis.

Your capabilities:
- Analyze controls, CUECs (Complementary User Entity Controls), and subservice organizations
- Explain framework mappings (AICPA TSC, COSO, ISO 27001, NIST CSF)
- Identify risks, deviations, and coverage gaps
- Compare findings across reports
- Provide actionable recommendations
- Reference the original PDF text and extraction logs when needed

Available resources:
- Structured data: Controls, CUECs, subservice orgs with metadata
- Executive summary: High-level report overview
- Original PDF text: Full extracted text from the SOC report
- Job artifacts: Extraction logs (output.txt) and detailed result JSONs

Guidelines:
- Be concise and specific - cite control IDs, CUEC numbers, and page references
- When discussing risks or deviations, highlight severity and business impact
- If asked about extraction issues, reference the output.txt logs
- If you don't have information, say so clearly
- Use bullet points for lists, tables for comparisons
- Prioritize clarity over formality

Available data context:
{context_description}

Current conversation is scoped to Scan ID {scan_id} ({company_name} - {product_name})."""


async def get_scan_context(db: AsyncSession, scan_id: int) -> Dict[str, Any]:
    """
    Retrieve comprehensive scan data for context building.
    
    Returns:
        Dictionary with scan metadata, controls, CUECs, etc.
    """
    # Get scan with relationships
    result = await db.execute(
        select(Scan)
        .where(Scan.id == scan_id)
    )
    scan = result.scalar_one_or_none()
    
    if not scan:
        raise ValueError(f"Scan {scan_id} not found")
    
    # Get company and product names from scan
    company_name = scan.company or "Unknown Company"
    product_name = scan.product or "Unknown Product"
    
    # Get controls
    controls_result = await db.execute(
        select(Control).where(Control.scan_id == scan_id)
    )
    controls = controls_result.scalars().all()
    
    # Get CUECs
    cuecs_result = await db.execute(
        select(CUEC).where(CUEC.scan_id == scan_id)
    )
    cuecs = cuecs_result.scalars().all()
    
    # Get subservice orgs
    suborgs_result = await db.execute(
        select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id)
    )
    suborgs = suborgs_result.scalars().all()
    
    # Build context
    context = {
        "scan_id": scan_id,
        "company_name": company_name,
        "product_name": product_name,
        "report_type": str(scan.report_type.value) if scan.report_type else "Unknown",
        "coverage_period": f"{scan.coverage_start} to {scan.coverage_end}" if scan.coverage_start else "Unknown",
        "total_controls": len(controls),
        "controls_with_deviations": sum(1 for c in controls if c.has_deviation),
        "total_cuecs": len(cuecs),
        "high_confidence_cuecs": sum(1 for c in cuecs if c.cuec_confidence and c.cuec_confidence >= 0.7),
        "low_confidence_cuecs": sum(1 for c in cuecs if c.cuec_confidence and c.cuec_confidence < 0.7),
        "total_subservice_orgs": len(suborgs),
        "detected_standards": scan.detected_standards or [],
        "active_frameworks": scan.active_frameworks or [],
        "controls": [
            {
                "id": c.control_id,
                "db_id": c.id,
                "description": c.control_desc[:200] if c.control_desc else None,
                "has_deviation": c.has_deviation,
                "deviation_desc": c.deviation_desc[:200] if c.deviation_desc else None,
                "primary_framework": c.primary_framework,
                "primary_criterion": c.primary_criterion_id,
                "page_refs": c.control_page_refs
            } for c in controls[:50]  # Limit to first 50 for token efficiency
        ],
        "cuecs": [
            {
                "seq": c.cuec_seq,
                "db_id": c.id,
                "description": c.cuec_description[:200] if c.cuec_description else None,
                "confidence": c.cuec_confidence,
                "primary_framework": c.primary_framework,
                "primary_criterion": c.primary_criterion_id,
                "control_strength": c.control_strength,
                "page_refs": c.cuec_page_refs
            } for c in cuecs[:50]  # Limit to first 50
        ],
        "subservice_orgs": [
            {
                "name": s.name,
                "confidence": s.confidence,
                "description": s.third_party_description[:200] if s.third_party_description else None
            } for s in suborgs[:20]
        ],
        "extracted_text": scan.extracted_text,  # Full PDF text
        "executive_summary": scan.executive_summary,  # Executive summary JSON
        "job_artifacts": await load_job_artifacts(scan_id)  # Job output files
    }
    
    return context


async def load_job_artifacts(scan_id: int) -> Dict[str, Any]:
    """
    Load job artifacts from the data/output directory.
    
    Returns:
        Dictionary with output.txt, result JSONs, and other artifacts
    """
    artifacts = {}
    output_dir = f"data/output/{scan_id}"
    
    if not os.path.exists(output_dir):
        logger.warning(f"Job artifacts directory not found: {output_dir}")
        return artifacts
    
    # Load output.txt (extraction logs)
    output_txt_path = os.path.join(output_dir, "output.txt")
    if os.path.exists(output_txt_path):
        try:
            with open(output_txt_path, 'r', encoding='utf-8') as f:
                # Get last 500 lines to avoid overwhelming context
                lines = f.readlines()
                artifacts['output_txt'] = ''.join(lines[-500:]) if len(lines) > 500 else ''.join(lines)
        except Exception as e:
            logger.error(f"Error reading output.txt: {e}")
    
    # Load result JSONs for detailed analysis
    json_files = ['control_result.json', 'cuec_result.json', 'combined_result.json']
    for json_file in json_files:
        json_path = os.path.join(output_dir, json_file)
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    artifacts[json_file.replace('.json', '')] = json.load(f)
            except Exception as e:
                logger.error(f"Error reading {json_file}: {e}")
    
    return artifacts


def build_context_summary(context: Dict[str, Any]) -> str:
    """Build human-readable context summary for system prompt."""
    summary_parts = [
        f"- Scan ID: {context['scan_id']}",
        f"- Company: {context['company_name']}",
        f"- Product: {context['product_name']}",
        f"- Report Type: {context['report_type']}",
        f"- Coverage Period: {context['coverage_period']}",
        f"- Total Controls: {context['total_controls']} ({context['controls_with_deviations']} with deviations)",
        f"- Total CUECs: {context['total_cuecs']} ({context['high_confidence_cuecs']} high confidence, {context['low_confidence_cuecs']} low confidence)",
        f"- Subservice Organizations: {context['total_subservice_orgs']}",
        f"- Detected Standards: {', '.join(context['detected_standards']) if context['detected_standards'] else 'None'}",
        f"- Active Frameworks: {', '.join(context['active_frameworks']) if context['active_frameworks'] else 'None'}"
    ]
    
    # Add resource availability info
    if context.get('extracted_text'):
        text_length = len(context['extracted_text'])
        summary_parts.append(f"- PDF Text Available: {text_length:,} characters")
    
    if context.get('executive_summary'):
        summary_parts.append("- Executive Summary: Available")
    
    if context.get('job_artifacts'):
        artifacts = context['job_artifacts']
        if artifacts.get('output_txt'):
            summary_parts.append("- Extraction Logs: Available (output.txt)")
        if any(k in artifacts for k in ['control_result', 'cuec_result', 'combined_result']):
            summary_parts.append("- Detailed Result JSONs: Available")
    
    return "\n".join(summary_parts)


def get_conversation_history(scan_id: int) -> List[Dict[str, str]]:
    """Get conversation history for a scan (session-scoped)."""
    return _conversation_sessions.get(scan_id, [])


def add_to_conversation(scan_id: int, role: str, content: str):
    """Add a message to conversation history."""
    if scan_id not in _conversation_sessions:
        _conversation_sessions[scan_id] = []
    
    _conversation_sessions[scan_id].append({
        "role": role,
        "content": content
    })
    
    # Trim history to last N messages
    if len(_conversation_sessions[scan_id]) > MAX_HISTORY_MESSAGES * 2:  # *2 for user+assistant pairs
        _conversation_sessions[scan_id] = _conversation_sessions[scan_id][-MAX_HISTORY_MESSAGES * 2:]


def clear_conversation(scan_id: int):
    """Clear conversation history for a scan."""
    if scan_id in _conversation_sessions:
        del _conversation_sessions[scan_id]


async def ask_grace(
    db: AsyncSession,
    scan_id: int,
    user_message: str,
    include_full_context: bool = False
) -> Dict[str, Any]:
    """
    Process a user message and get GRaCe's response.
    
    Args:
        db: Database session
        scan_id: Scan to query about
        user_message: User's question
        include_full_context: If True, include full scan data in context (more tokens, more accurate)
    
    Returns:
        Dictionary with response, tokens used, and context
    """
    try:
        # Get scan context
        context = await get_scan_context(db, scan_id)
        
        # Build system prompt
        context_summary = build_context_summary(context)
        system_prompt = GRACE_SYSTEM_PROMPT.format(
            context_description=context_summary,
            scan_id=scan_id,
            company_name=context['company_name'],
            product_name=context['product_name']
        )
        
        # Build conversation context
        history = get_conversation_history(scan_id)
        conversation_text = ""
        for msg in history:
            role = "User" if msg["role"] == "user" else "Assistant"
            conversation_text += f"\n{role}: {msg['content']}"
        
        # Build full prompt
        full_prompt = f"""{system_prompt}

Previous conversation:
{conversation_text if conversation_text else "(This is the start of the conversation)"}

Current user question: {user_message}

Please provide a helpful, accurate response based on the scan context provided."""
        
        # Intelligently add resources based on question content
        user_message_lower = user_message.lower()
        
        # Add PDF text for questions about report content/sections
        if any(keyword in user_message_lower for keyword in ['section', 'report text', 'pdf', 'page', 'quote', 'exact', 'what does', 'find in']):
            if context.get('extracted_text'):
                # Provide a sample of PDF text (first 5000 chars)
                pdf_sample = context['extracted_text'][:5000]
                full_prompt += f"\n\n[PDF Text Sample - First 5000 characters]:\n{pdf_sample}\n(Note: Full text available upon request)"
        
        # Add extraction logs for questions about processing/errors
        if any(keyword in user_message_lower for keyword in ['extraction', 'error', 'log', 'processing', 'failed', 'issue', 'problem']):
            if context.get('job_artifacts', {}).get('output_txt'):
                full_prompt += f"\n\n[Extraction Logs - Last portion]:\n{context['job_artifacts']['output_txt'][-3000:]}"
        
        # Add executive summary for high-level questions
        if any(keyword in user_message_lower for keyword in ['summary', 'overview', 'about', 'describe']):
            if context.get('executive_summary'):
                full_prompt += f"\n\n[Executive Summary]:\n{json.dumps(context['executive_summary'], indent=2)}"
        
        # Add detailed context if requested (for complex queries)
        if include_full_context:
            full_prompt += f"\n\nDetailed Context:\n{json.dumps(context, indent=2, default=str)}"
        
        # Call GPT
        logger.info(f"GRaCe processing message for scan {scan_id}: {user_message[:100]}")
        
        assistant_message = gpt_extract(full_prompt, "grace_chat")
        
        # Add to conversation history
        add_to_conversation(scan_id, "user", user_message)
        add_to_conversation(scan_id, "assistant", assistant_message)
        
        logger.info(f"GRaCe response generated for scan {scan_id}")
        
        return {
            "response": assistant_message,
            "conversation_length": len(get_conversation_history(scan_id)),
            "context_included": include_full_context
        }
        
    except Exception as e:
        logger.error(f"Error in ask_grace: {str(e)}", exc_info=True)
        return {
            "response": f"I encountered an error: {str(e)}. Please try again or rephrase your question.",
            "error": str(e),
            "conversation_length": 0
        }
