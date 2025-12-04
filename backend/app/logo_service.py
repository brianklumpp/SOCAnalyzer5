"""
Logo Service - Fetch and cache company logos from Clearbit API
"""

import logging
import requests
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from .models import Company

logger = logging.getLogger(__name__)

CLEARBIT_LOGO_API = "https://logo.clearbit.com/{domain}"
REQUEST_TIMEOUT = 5  # seconds


def fetch_and_cache_logo(
    company_id: int,
    domain: Optional[str],
    db: Session
) -> Tuple[bool, Optional[str]]:
    """
    Fetch company logo from Clearbit API and cache in database.
    
    Args:
        company_id: Database ID of the company
        domain: Company domain (e.g., "okta.com")
        db: Database session
        
    Returns:
        Tuple of (success: bool, logo_url: Optional[str])
    """
    if not domain:
        logger.info(f"[LOGO_SERVICE] No domain provided for company_id={company_id}, skipping logo fetch")
        return False, None
    
    # Check if logo already cached
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        logger.error(f"[LOGO_SERVICE] Company not found: company_id={company_id}")
        return False, None
    
    if company.logo_url:
        logger.info(f"[LOGO_SERVICE] Logo already cached for {domain}: {company.logo_url}")
        return True, company.logo_url
    
    # Fetch from Clearbit
    logo_url = CLEARBIT_LOGO_API.format(domain=domain)
    
    try:
        logger.info(f"[LOGO_SERVICE] Fetching logo for {domain} from Clearbit...")
        response = requests.head(logo_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        
        if response.status_code == 200:
            # Logo found, cache it
            company.logo_url = logo_url
            db.commit()
            logger.info(f"[LOGO_SERVICE] Logo cached successfully: {logo_url}")
            return True, logo_url
        else:
            logger.info(f"[LOGO_SERVICE] No logo found for {domain} (status={response.status_code})")
            return False, None
            
    except requests.exceptions.Timeout:
        logger.warning(f"[LOGO_SERVICE] Timeout fetching logo for {domain}")
        return False, None
    except Exception as e:
        logger.error(f"[LOGO_SERVICE] Error fetching logo for {domain}: {e}", exc_info=True)
        return False, None


def fetch_logo_with_gpt(
    company_id: int,
    company_name: str,
    domain: Optional[str],
    db: Session
) -> Tuple[bool, Optional[str]]:
    """
    Use GPT to determine logo URL for a company.
    
    Args:
        company_id: Database ID of the company
        company_name: Company name
        domain: Company domain (e.g., "okta.com")
        db: Database session
        
    Returns:
        Tuple of (success: bool, logo_url: Optional[str])
    """
    from .gpt_client import gpt_extract
    import json
    
    if not domain and not company_name:
        logger.info(f"[LOGO_SERVICE_GPT] No domain or name for company_id={company_id}")
        return False, None
    
    # Check if logo already cached
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return False, None
    
    if company.logo_url:
        logger.info(f"[LOGO_SERVICE_GPT] Logo already cached: {company.logo_url}")
        return True, company.logo_url
    
    # Build GPT prompt
    prompt = f"""You are a logo URL expert. Determine the most likely logo URL for this company.

Company Name: {company_name}
Domain: {domain or 'Unknown'}

## Common Logo URL Patterns
1. Clearbit API: https://logo.clearbit.com/{{domain}}
2. Google Favicon: https://www.google.com/s2/favicons?domain={{domain}}&sz=128

## Instructions
1. If domain is provided, use Clearbit format: https://logo.clearbit.com/{{domain}}
2. Return the single most likely URL
3. If uncertain, return the Clearbit URL as fallback

## Output Format
Return ONLY a JSON object (no markdown, no explanatory text):
{{
    "logo_url": "https://...",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}
"""
    
    try:
        logger.info(f"[LOGO_SERVICE_GPT] Asking GPT for logo URL: {company_name} ({domain})")
        response = gpt_extract(prompt, "logo_extractor")
        
        # Parse GPT response
        response_clean = response.strip()
        if response_clean.startswith('```'):
            import re
            json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_clean, re.DOTALL)
            if json_match:
                response_clean = json_match.group(1)
        
        data = json.loads(response_clean)
        logo_url = data.get("logo_url")
        confidence = data.get("confidence", 0.5)
        
        if logo_url and confidence >= 0.5:
            # Validate URL is reachable
            try:
                r = requests.head(logo_url, timeout=5, allow_redirects=True)
                if r.status_code == 200:
                    company.logo_url = logo_url
                    db.commit()
                    logger.info(f"[LOGO_SERVICE_GPT] ✓ Logo cached: {logo_url} (confidence={confidence})")
                    return True, logo_url
                else:
                    logger.warning(f"[LOGO_SERVICE_GPT] URL not reachable ({r.status_code}): {logo_url}")
                    # Cache anyway if high confidence (Strategy A)
                    if confidence >= 0.8:
                        company.logo_url = logo_url
                        db.commit()
                        logger.info(f"[LOGO_SERVICE_GPT] ✓ Cached high-confidence URL despite validation failure")
                        return True, logo_url
                    return False, None
            except Exception as req_err:
                logger.warning(f"[LOGO_SERVICE_GPT] Failed to validate URL: {req_err}")
                # Cache anyway if high confidence (Strategy A)
                if confidence >= 0.8:
                    company.logo_url = logo_url
                    db.commit()
                    logger.info(f"[LOGO_SERVICE_GPT] ✓ Cached high-confidence URL despite validation error")
                    return True, logo_url
                return False, None
        else:
            logger.info(f"[LOGO_SERVICE_GPT] Low confidence ({confidence}) or no URL")
            return False, None
            
    except Exception as e:
        logger.error(f"[LOGO_SERVICE_GPT] Error: {e}", exc_info=True)
        return False, None


def get_company_logo_url(company_id: int, db: Session) -> Optional[str]:
    """
    Get cached logo URL for a company.
    
    Args:
        company_id: Database ID of the company
        db: Database session
        
    Returns:
        Logo URL if cached, None otherwise
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if company:
        return company.logo_url
    return None
