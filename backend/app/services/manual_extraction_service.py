"""
Manual Extraction Service
Handles targeted extraction of CUECs/Subservice Orgs from specific PDF pages.
"""
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Tuple
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import Scan, CUEC, SubserviceOrg
from .. import config

logger = logging.getLogger(__name__)


def parse_page_ranges(pages_str: str) -> List[int]:
    """
    Parse page range string into list of page numbers.
    
    Examples:
        "5" -> [5]
        "5,7,9" -> [5, 7, 9]
        "5-8" -> [5, 6, 7, 8]
        "5, 7-9, 12" -> [5, 7, 8, 9, 12]
    
    Args:
        pages_str: Comma/space separated page numbers and ranges
        
    Returns:
        Sorted list of unique page numbers
        
    Raises:
        ValueError: If format is invalid
    """
    if not pages_str or not pages_str.strip():
        raise ValueError("Page specification cannot be empty")
    
    pages = set()
    parts = re.split(r'[,\s]+', pages_str.strip())
    
    for part in parts:
        if not part:
            continue
            
        # Check for range (e.g., "5-8")
        if '-' in part:
            try:
                start, end = part.split('-', 1)
                start_page = int(start.strip())
                end_page = int(end.strip())
                
                if start_page < 1 or end_page < 1:
                    raise ValueError(f"Page numbers must be positive: {part}")
                if start_page > end_page:
                    raise ValueError(f"Invalid range (start > end): {part}")
                    
                pages.update(range(start_page, end_page + 1))
            except ValueError as e:
                raise ValueError(f"Invalid page range '{part}': {e}")
        else:
            # Single page number
            try:
                page_num = int(part.strip())
                if page_num < 1:
                    raise ValueError(f"Page number must be positive: {part}")
                pages.add(page_num)
            except ValueError:
                raise ValueError(f"Invalid page number: {part}")
    
    if not pages:
        raise ValueError("No valid page numbers found")
    
    return sorted(list(pages))


def extract_text_from_pages(pdf_bytes: bytes, page_numbers: List[int]) -> str:
    """
    Extract text from specific pages of a PDF.
    
    Args:
        pdf_bytes: PDF file bytes
        page_numbers: List of 1-indexed page numbers to extract
        
    Returns:
        Concatenated text from specified pages
    """
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        extracted_text = []
        
        for page_num in page_numbers:
            # fitz uses 0-indexed pages
            if 0 <= page_num - 1 < doc.page_count:
                page = doc[page_num - 1]
                text = page.get_text()
                extracted_text.append(f"\n=== PAGE {page_num} ===\n{text}")
            else:
                logger.warning(f"Page {page_num} out of range (PDF has {doc.page_count} pages)")
        
        doc.close()
        return "\n".join(extracted_text)
        
    except Exception as e:
        logger.error(f"Failed to extract text from PDF pages: {e}")
        raise


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two text strings using SequenceMatcher.
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Similarity score (0.0 - 1.0)
    """
    if not text1 or not text2:
        return 0.0
    
    # Normalize: lowercase, strip whitespace
    t1 = text1.lower().strip()
    t2 = text2.lower().strip()
    
    return SequenceMatcher(None, t1, t2).ratio()


def log_manual_extraction(scan_id: int, entity_type: str, pages: List[int], 
                          username: str, results: Dict[str, Any]):
    """
    Log manual extraction operation to separate log file.
    
    Args:
        scan_id: Scan ID
        entity_type: "cuec" or "subservice_org"
        pages: List of extracted page numbers
        username: User who performed extraction
        results: Extraction results summary
    """
    try:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "scan_id": scan_id,
            "entity_type": entity_type,
            "pages": pages,
            "page_count": len(pages),
            "username": username,
            "results": results
        }
        
        import json
        with open(config.MANUAL_EXTRACTION_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
            
    except Exception as e:
        logger.warning(f"Failed to log manual extraction: {e}")


async def manual_extract_cuecs(
    scan_id: int,
    pages: List[int],
    db: Session,
    username: str
) -> Dict[str, Any]:
    """
    Manually extract CUECs from specific PDF pages.
    
    Args:
        scan_id: Scan ID
        pages: List of page numbers to extract from
        db: Database session
        username: Username performing extraction
        
    Returns:
        Dict with new_count, updated_count, invalidated_count, items
    """
    from ..extractors.cuec_extractor import extract_cuecs
    from ..frameworks import map_cuec_to_frameworks_dynamic, get_available_frameworks
    
    # Get scan and PDF
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    
    if not scan:
        raise ValueError(f"Scan {scan_id} not found")
    
    if not scan.pdf_file:
        raise ValueError(f"PDF not available for scan {scan_id}")
    
    # Use PDF page numbers directly (no offset adjustment)
    print(f"[MANUAL_EXTRACT PRINT] Extracting from PDF pages: {pages}")
    logger.info(f"[MANUAL_EXTRACT CUEC] Extracting text from pages: {pages}")
    extracted_text = extract_text_from_pages(scan.pdf_file, pages)
    print(f"[MANUAL_EXTRACT PRINT] Extracted text length: {len(extracted_text)} chars")
    print(f"[MANUAL_EXTRACT PRINT] FULL EXTRACTED TEXT:")
    print(extracted_text)
    print(f"[MANUAL_EXTRACT PRINT] === END OF EXTRACTED TEXT ===")
    logger.info(f"[MANUAL_EXTRACT CUEC] Extracted text length: {len(extracted_text)} chars, preview: {extracted_text[:200]}")
    
    # Create temporary job paths structure for extractor
    import tempfile
    import os
    from pathlib import Path
    import json
    
    temp_dir = Path(tempfile.mkdtemp(prefix='manual_extract_'))
    json_dir = temp_dir / 'json'
    json_dir.mkdir(exist_ok=True)
    
    try:
        # Create job paths dict
        job_paths = {
            'temp_dir': temp_dir,
            'json_dir': json_dir
        }
        
        job_id = f"manual_extract_{scan_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Write extracted text to temp file
        output_txt = temp_dir / 'output.txt'
        with open(output_txt, 'w', encoding='utf-8') as f:
            f.write(extracted_text)
        
        # Count lines for section_results.json
        text_lines = extracted_text.split('\n')
        line_count = len(text_lines)
        
        # Create minimal section_results.json for extractor
        # The extractor looks for Description_of_System section
        sections = [{
            "topic": "Description_of_System",
            "start_line": 1,
            "end_line": line_count,
            "DOC_page_ref": pages[0],
            "end_DOC_page_ref": pages[-1],
            "content": extracted_text[:500]  # Preview for logging
        }]
        
        section_json = json_dir / 'section_results.json'
        with open(section_json, 'w', encoding='utf-8') as f:
            json.dump(sections, f)
        
        # Run CUEC extractor (skip framework mapping and chunking for performance and accuracy)
        logger.info(f"[MANUAL_EXTRACT] Running CUEC extractor on {len(pages)} pages (skip_framework_mapping=True, disable_chunking=True)")
        extract_cuecs(
            report_type=scan.report_type or "SOC2",
            job_paths=job_paths,
            job_id=job_id,
            redis_client=None,
            skip_framework_mapping=True,
            disable_chunking=True
        )
        
        # Read results from cuec_result.json
        cuec_result_json = json_dir / 'cuec_result.json'
        print(f"[MANUAL_EXTRACT PRINT] Looking for cuec_result.json at: {cuec_result_json}")
        print(f"[MANUAL_EXTRACT PRINT] File exists: {cuec_result_json.exists()}")
        if cuec_result_json.exists():
            with open(cuec_result_json, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                print(f"[MANUAL_EXTRACT PRINT] Raw result_data type: {type(result_data)}, keys: {result_data.keys() if isinstance(result_data, dict) else 'N/A'}")
                logger.info(f"[MANUAL_EXTRACT] Raw result_data type: {type(result_data)}, keys: {result_data.keys() if isinstance(result_data, dict) else 'N/A'}")
                # The extractor writes {"cuecs": [...]} format
                if isinstance(result_data, dict):
                    extracted_cuecs = result_data.get('cuecs', [])
                elif isinstance(result_data, list):
                    extracted_cuecs = result_data
                else:
                    extracted_cuecs = []
                print(f"[MANUAL_EXTRACT PRINT] Parsed extracted_cuecs count: {len(extracted_cuecs)}")
        else:
            print(f"[MANUAL_EXTRACT PRINT] cuec_result.json NOT FOUND")
            logger.warning(f"[MANUAL_EXTRACT] cuec_result.json not found at {cuec_result_json}")
            extracted_cuecs = []
        
        print(f"[MANUAL_EXTRACT PRINT] Total extracted CUECs: {len(extracted_cuecs)}")
        logger.info(f"[MANUAL_EXTRACT] Extracted {len(extracted_cuecs)} CUECs from pages {pages}")
        
        # DISABLED: Framework mapping is too slow for manual extracts
        # Framework mapping can be run later as a batch operation if needed
        # Get available frameworks for mapping
        # available_frameworks = get_available_frameworks(scan.report_type or "SOC2")
        # 
        # # Map to frameworks
        # for cuec in extracted_cuecs:
        #     # Ensure cuec is a dict
        #     if not isinstance(cuec, dict):
        #         logger.warning(f"[MANUAL_EXTRACT] Skipping non-dict CUEC: {type(cuec)}")
        #         continue
        #     if cuec.get('cuec_description'):
        #         mapping_result = map_cuec_to_frameworks_dynamic(
        #             cuec_desc=cuec['cuec_description'],
        #             cuec_id=str(cuec.get('cuec_seq', 'unknown')),
        #             available_frameworks=available_frameworks,
        #             top_k=5
        #         )
        #         cuec['framework_mappings'] = mapping_result.get('framework_mappings', {})
        #         cuec['primary_framework'] = mapping_result.get('primary_framework')
        #         cuec['primary_criterion_id'] = mapping_result.get('primary_criterion_id')
        #         cuec['primary_confidence'] = mapping_result.get('primary_confidence')
        
        logger.info(f"[MANUAL_EXTRACT] Skipping framework mapping for manual extracts (performance optimization)")
        
        # Process results: deduplicate and boost confidence
        new_count = 0
        updated_count = 0
        items = []
        
        # Get existing CUECs for this scan
        existing_result = await db.execute(
            select(CUEC).where(CUEC.scan_id == scan_id)
        )
        existing_cuecs = existing_result.scalars().all()
        
        for extracted_cuec in extracted_cuecs:
            # Ensure it's a dict
            if not isinstance(extracted_cuec, dict):
                logger.warning(f"[MANUAL_EXTRACT] Skipping non-dict item: {type(extracted_cuec)}")
                continue
                
            desc = extracted_cuec.get('cuec_description', '')
            if not desc:
                continue
            
            # Check for duplicates
            best_match = None
            best_similarity = 0.0
            
            for existing in existing_cuecs:
                if existing.cuec_description:
                    similarity = calculate_similarity(desc, existing.cuec_description)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = existing
            
            # Apply confidence boost
            base_confidence = extracted_cuec.get('cuec_confidence', 0.85)
            boosted_confidence = min(1.0, max(
                config.HIGH_CONFIDENCE_THRESHOLD,
                base_confidence + config.MANUAL_EXTRACTION_CONFIDENCE_BOOST
            ))
            
            if best_match and best_similarity >= config.MANUAL_EXTRACTION_SIMILARITY_THRESHOLD:
                # Update existing
                old_confidence = best_match.cuec_confidence or 0.0
                best_match.cuec_confidence = boosted_confidence
                
                edit_note = f"Manual extraction from pages {','.join(map(str, pages))} " \
                           f"(User: {username}, Date: {datetime.utcnow().strftime('%Y-%m-%d')}, " \
                           f"Confidence: {old_confidence:.2f}→{boosted_confidence:.2f})"
                
                if best_match.edit_log:
                    best_match.edit_log += f",\n{edit_note}"
                else:
                    best_match.edit_log = edit_note
                
                updated_count += 1
                items.append({"id": best_match.id, "description": desc[:100], "action": "updated"})
                
            else:
                # Insert new
                new_cuec = CUEC(
                    scan_id=scan_id,
                    cuec_seq=len(existing_cuecs) + new_count + 1,
                    cuec_description=desc,
                    cuec_confidence=boosted_confidence,
                    cuec_page_refs=extracted_cuec.get('cuec_page_refs'),
                    cuec_line_ref=extracted_cuec.get('cuec_line_ref'),
                    framework_mappings=extracted_cuec.get('framework_mappings'),
                    primary_framework=extracted_cuec.get('primary_framework'),
                    primary_criterion_id=extracted_cuec.get('primary_criterion_id'),
                    primary_confidence=extracted_cuec.get('primary_confidence'),
                    edit_log=f"Manual extraction from pages {','.join(map(str, pages))} " \
                            f"(User: {username}, Date: {datetime.utcnow().strftime('%Y-%m-%d')})"
                )
                db.add(new_cuec)
                new_count += 1
                items.append({"description": desc[:100], "action": "created"})
        
        await db.commit()
        
        # Phase 2: Invalidate high-confidence items NOT on specified pages
        invalidated_count = 0
        for existing in existing_cuecs:
            if existing.cuec_confidence and existing.cuec_confidence >= config.HIGH_CONFIDENCE_THRESHOLD:
                # Check if this CUEC's pages overlap with specified pages
                if existing.cuec_page_refs:
                    # Parse page refs (could be "5", "5,6", "5-7", etc.)
                    try:
                        existing_pages = parse_page_ranges(existing.cuec_page_refs)
                        # If no overlap with specified pages, invalidate
                        if not any(p in pages for p in existing_pages):
                            existing.cuec_confidence = 0.0
                            
                            edit_note = f"Confidence reset - not found during manual extraction of pages " \
                                       f"{','.join(map(str, pages))} (User: {username}, Date: {datetime.utcnow().strftime('%Y-%m-%d')})"
                            
                            if existing.edit_log:
                                existing.edit_log += f",\n{edit_note}"
                            else:
                                existing.edit_log = edit_note
                            
                            invalidated_count += 1
                            items.append({"id": existing.id, "description": (existing.cuec_description or '')[:100], "action": "invalidated"})
                    except:
                        # If we can't parse page refs, leave it alone
                        pass
        
        await db.commit()
        
        results = {
            "new_count": new_count,
            "updated_count": updated_count,
            "invalidated_count": invalidated_count,
            "items": items
        }
        
        # Log operation
        log_manual_extraction(scan_id, "cuec", pages, username, results)
        
        return results
        
    finally:
        # Cleanup temp directory
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


async def manual_extract_subservice_orgs(
    scan_id: int,
    pages: List[int],
    db: Session,
    username: str
) -> Dict[str, Any]:
    """
    Manually extract Subservice Organizations from specific PDF pages.
    
    Similar to manual_extract_cuecs but for subservice orgs (no framework mapping needed).
    """
    from ..extractors.subservice_orgs import extract_subservice_orgs
    
    # Get scan and PDF
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    
    if not scan:
        raise ValueError(f"Scan {scan_id} not found")
    
    if not scan.pdf_file:
        raise ValueError(f"PDF not available for scan {scan_id}")
    
    # Use PDF page numbers directly (no offset adjustment)
    logger.info(f"[MANUAL_EXTRACT SO] Extracting text from pages: {pages}")
    extracted_text = extract_text_from_pages(scan.pdf_file, pages)
    logger.info(f"[MANUAL_EXTRACT SO] Extracted text length: {len(extracted_text)} chars, preview: {extracted_text[:200]}")
    
    # Create temporary job paths structure for extractor
    import tempfile
    import os
    from pathlib import Path
    import json
    
    temp_dir = Path(tempfile.mkdtemp(prefix='manual_extract_so_'))
    json_dir = temp_dir / 'json'
    json_dir.mkdir(exist_ok=True)
    
    try:
        # Create job paths dict
        job_paths = {
            'temp_dir': temp_dir,
            'json_dir': json_dir
        }
        
        job_id = f"manual_extract_so_{scan_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Write extracted text to temp file
        output_txt = temp_dir / 'output.txt'
        with open(output_txt, 'w', encoding='utf-8') as f:
            f.write(extracted_text)
        
        # Create minimal section_results.json for extractor
        sections = [{
            "topic": "Description_of_System",
            "DOC_page_ref": pages[0],
            "end_DOC_page_ref": pages[-1],
            "content": extracted_text[:500]
        }]
        
        section_json = json_dir / 'section_results.json'
        with open(section_json, 'w', encoding='utf-8') as f:
            json.dump(sections, f)
        
        # Run extractor (disable chunking for manual extractions)
        logger.info(f"[MANUAL_EXTRACT] Running Subservice Org extractor on {len(pages)} pages (disable_chunking=True)")
        extract_subservice_orgs(
            job_paths=job_paths,
            job_id=job_id,
            redis_client=None,
            disable_chunking=True
        )
        
        # Read results
        so_result_json = json_dir / 'subservice_orgs_result.json'
        if so_result_json.exists():
            with open(so_result_json, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                # The extractor writes {"subservice_orgs": [...]} format
                if isinstance(result_data, dict):
                    extracted_orgs = result_data.get('subservice_orgs', [])
                elif isinstance(result_data, list):
                    extracted_orgs = result_data
                else:
                    extracted_orgs = []
        else:
            extracted_orgs = []
        
        logger.info(f"[MANUAL_EXTRACT] Extracted {len(extracted_orgs)} subservice orgs")
        
        # Process results
        new_count = 0
        updated_count = 0
        items = []
        
        # Get existing orgs
        existing_result = await db.execute(
            select(SubserviceOrg).where(SubserviceOrg.scan_id == scan_id)
        )
        existing_orgs = existing_result.scalars().all()
        
        for extracted_org in extracted_orgs:
            # Ensure it's a dict
            if not isinstance(extracted_org, dict):
                logger.warning(f"[MANUAL_EXTRACT] Skipping non-dict org: {type(extracted_org)}")
                continue
                
            # Extractor uses 'third_party_name' field
            name = extracted_org.get('third_party_name', '') or extracted_org.get('name', '')
            if not name:
                continue
            
            # Check duplicates
            best_match = None
            best_similarity = 0.0
            
            for existing in existing_orgs:
                if existing.name:
                    similarity = calculate_similarity(name, existing.name)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = existing
            
            # Boost confidence - extractor uses 'third_party_confidence'
            base_confidence = extracted_org.get('third_party_confidence', extracted_org.get('confidence', 0.85))
            boosted_confidence = min(1.0, max(
                config.HIGH_CONFIDENCE_THRESHOLD,
                base_confidence + config.MANUAL_EXTRACTION_CONFIDENCE_BOOST
            ))
            
            if best_match and best_similarity >= config.MANUAL_EXTRACTION_SIMILARITY_THRESHOLD:
                # Update
                old_confidence = best_match.confidence or 0.0
                best_match.confidence = boosted_confidence
                
                edit_note = f"Manual extraction from pages {','.join(map(str, pages))} " \
                           f"(User: {username}, Date: {datetime.utcnow().strftime('%Y-%m-%d')}, " \
                           f"Confidence: {old_confidence:.2f}→{boosted_confidence:.2f})"
                
                if best_match.edit_log:
                    best_match.edit_log += f",\n{edit_note}"
                else:
                    best_match.edit_log = edit_note
                
                updated_count += 1
                items.append({"id": best_match.id, "name": name[:100], "action": "updated"})
                
            else:
                # Insert new
                # Convert page_ref to string if it's a list
                page_ref = extracted_org.get('third_party_page_ref')
                if isinstance(page_ref, list):
                    page_ref = ','.join(map(str, page_ref))
                elif page_ref is not None:
                    page_ref = str(page_ref)
                
                new_org = SubserviceOrg(
                    scan_id=scan_id,
                    name=name,
                    confidence=boosted_confidence,
                    third_party_description=extracted_org.get('third_party_description'),
                    third_party_page_ref=page_ref,
                    edit_log=f"Manual extraction from pages {','.join(map(str, pages))} " \
                            f"(User: {username}, Date: {datetime.utcnow().strftime('%Y-%m-%d')})"
                )
                db.add(new_org)
                new_count += 1
                items.append({"name": name[:100], "action": "created"})
        
        await db.commit()
        
        # Phase 2: Invalidate high-confidence items NOT on specified pages
        invalidated_count = 0
        for existing in existing_orgs:
            if existing.confidence and existing.confidence >= config.HIGH_CONFIDENCE_THRESHOLD:
                if existing.third_party_page_ref:
                    try:
                        existing_pages = parse_page_ranges(existing.third_party_page_ref)
                        if not any(p in pages for p in existing_pages):
                            existing.confidence = 0.0
                            
                            edit_note = f"Confidence reset - not found during manual extraction of pages " \
                                       f"{','.join(map(str, pages))} (User: {username}, Date: {datetime.utcnow().strftime('%Y-%m-%d')})"
                            
                            if existing.edit_log:
                                existing.edit_log += f",\n{edit_note}"
                            else:
                                existing.edit_log = edit_note
                            
                            invalidated_count += 1
                            items.append({"id": existing.id, "name": (existing.name or '')[:100], "action": "invalidated"})
                    except:
                        pass
        
        await db.commit()
        
        results = {
            "new_count": new_count,
            "updated_count": updated_count,
            "invalidated_count": invalidated_count,
            "items": items
        }
        
        log_manual_extraction(scan_id, "subservice_org", pages, username, results)
        
        return results
        
    finally:
        # Cleanup temp directory
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
