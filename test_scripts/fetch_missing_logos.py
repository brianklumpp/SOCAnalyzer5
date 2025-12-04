"""
Fetch logos for scans that are missing them
"""
import sys
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app import config
from app.models import Company
from app.logo_service import fetch_logo_with_gpt

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_missing_logos():
    """Fetch logos for companies that don't have them"""
    # Create sync engine
    sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
    engine = create_engine(sync_db_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    
    with SessionLocal() as session:
        # Find companies without logos
        companies = session.query(Company).filter(
            (Company.logo_url == None) | (Company.logo_url == '')
        ).all()
        
        logger.info(f"Found {len(companies)} companies without logos")
        
        for company in companies:
            logger.info(f"Processing company: {company.name} (ID: {company.id})")
            
            # Try to infer domain from company name if not set
            domain = company.company_domain
            if not domain and company.name:
                # Common domain patterns
                name_lower = company.name.lower()
                if 'deloitte' in name_lower:
                    domain = 'deloitte.com'
                elif 'adobe' in name_lower:
                    domain = 'adobe.com'
                else:
                    # Try to extract domain-like name
                    # Remove common suffixes
                    for suffix in [' llp', ' llc', ' inc', ' incorporated', ' corporation', ' corp']:
                        if name_lower.endswith(suffix):
                            name_lower = name_lower[:-len(suffix)].strip()
                            break
                    # Use as domain with .com
                    domain = name_lower.replace(' ', '') + '.com'
                
                logger.info(f"  Inferred domain: {domain}")
                # Update company with inferred domain
                company.company_domain = domain
                session.commit()
            
            if domain:
                try:
                    success, logo_url = fetch_logo_with_gpt(company.id, company.name, domain, session)
                    if success:
                        logger.info(f"  ✓ Successfully fetched logo: {logo_url}")
                    else:
                        logger.warning(f"  ✗ Failed to fetch logo for {company.name}")
                except Exception as e:
                    logger.error(f"  ✗ Error fetching logo for {company.name}: {e}")
            else:
                logger.warning(f"  ✗ No domain available for {company.name}")
        
        session.commit()
        logger.info("Logo fetching complete!")

if __name__ == "__main__":
    fetch_missing_logos()
