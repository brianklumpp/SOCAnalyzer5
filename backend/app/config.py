# --- All imports at the top (PEP8 best practice) ---
import os
import pathlib
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL_ASYNC")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set. Please set it in your .env file.")

# Schema/migration startup behavior
AUTO_CREATE_SCHEMA = os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true"
RUN_MIGRATIONS_ON_START = os.getenv("RUN_MIGRATIONS_ON_START", "false").lower() == "true"
ALEMBIC_INI_PATH = os.getenv("ALEMBIC_INI_PATH", str(pathlib.Path(__file__).resolve().parents[1] / 'alembic.ini'))

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
EXCLUDE_ACCESS_LOG_PATHS = [s.strip() for s in os.getenv("EXCLUDE_ACCESS_LOG_PATHS", "/analyze/status").split(",") if s.strip()]

# --- GPT logging controls (opt-in, safe by default) ---
# Enable a unified JSONL log of GPT requests/responses at data/logs/gpt_calls.log
LOG_GPT_REQUESTS = os.getenv("LOG_GPT_REQUESTS", "false").lower() == "true"
# When enabled, include a truncated prompt excerpt; set to false to log only sizes/metadata
LOG_GPT_PROMPTS = os.getenv("LOG_GPT_PROMPTS", "false").lower() == "true"
# Max characters to include from prompt/response excerpts in logs
LOG_GPT_MAX_PROMPT_CHARS = int(os.getenv("LOG_GPT_MAX_PROMPT_CHARS", "800"))
LOG_GPT_MAX_RESPONSE_CHARS = int(os.getenv("LOG_GPT_MAX_RESPONSE_CHARS", "800"))
# Sample rate for logging (0.0–1.0). 1.0 = log all calls; 0.1 = ~10% of calls
LOG_GPT_SAMPLE_RATE = float(os.getenv("LOG_GPT_SAMPLE_RATE", "1.0"))
GPT_CALLS_LOG_PATH = str((pathlib.Path(__file__).resolve().parents[2] / 'data/logs/gpt_calls.log').resolve())
# Include selected response/request headers (rate-limit diagnostics) when logging
LOG_GPT_INCLUDE_HEADERS = os.getenv("LOG_GPT_INCLUDE_HEADERS", "false").lower() == "true"
# Comma-separated header names to capture (case-insensitive). Defaults target common rate limit & retry headers.
LOG_GPT_HEADER_WHITELIST = [h.strip() for h in os.getenv(
    "LOG_GPT_HEADER_WHITELIST",
    "x-ratelimit-limit,x-ratelimit-remaining,x-ratelimit-reset,retry-after"
).split(',') if h.strip()]

# --- Project policy toggles ---
# IMPORTANT: Per project policy, DO NOT use regex/text-heuristic fallbacks to produce outputs when GPT fails.
# Keep extractors GPT-driven. If a fallback is ever needed for debugging, flip this flag to true temporarily.
ALLOW_REGEX_FALLBACKS = os.getenv("ALLOW_REGEX_FALLBACKS", "false").lower() == "true"

# --- LLM Provider Selection ---
# Provider options: 'openai' | 'azure' | 'dataiku_apinode' | 'dataiku_dss'
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "dataiku_dss")

# Azure OpenAI (optional if using Azure directly)
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")  # e.g., https://<resource>.openai.azure.com
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENTS = {
    # Map logical model names to Azure deployment names if used directly
    "gpt-4o": os.getenv("AZURE_OPENAI_DEPLOYMENT_GPT4O"),
    "gpt-3.5-turbo": os.getenv("AZURE_OPENAI_DEPLOYMENT_GPT35"),
    "gpt-5": os.getenv("AZURE_OPENAI_DEPLOYMENT_GPT5"),
}

# Dataiku API Node configuration (recommended for corp environment)
DATAIKU_API_BASE = os.getenv("DATAIKU_API_BASE")  # e.g., https://dataiku-dss.corp.nandps.com/public/api/v1
DATAIKU_API_KEY = os.getenv("DATAIKU_API_KEY")
DATAIKU_SERVICE_ID = os.getenv("DATAIKU_SERVICE_ID", "SOLIDIGM_GPT_API_ACCESS")
DATAIKU_ENDPOINT_ID = os.getenv("DATAIKU_ENDPOINT_ID", "chat-completions")
DATAIKU_TIMEOUT = float(os.getenv("DATAIKU_TIMEOUT", "120"))
DATAIKU_VERIFY_SSL = os.getenv("DATAIKU_VERIFY_SSL", "true").lower() == "true"
DATAIKU_CA_BUNDLE = os.getenv("DATAIKU_CA_BUNDLE")  # optional custom CA path

# Dataiku DSS (Python client) configuration
DATAIKU_DSS_HOST = os.getenv("DATAIKU_DSS_HOST")  # e.g., https://dataiku-dss.corp.nandps.com/
DATAIKU_DSS_HOST_IP = os.getenv("DATAIKU_DSS_HOST_IP")  # Optional: fallback IP address (e.g., "192.168.1.100")
DATAIKU_DSS_API_KEY = os.getenv("DATAIKU_DSS_API_KEY")
DATAIKU_DSS_PROJECT = os.getenv("DATAIKU_DSS_PROJECT", "SOLIDIGM_GPT_API_ACCESS")

# Dataiku LLM Catalog mapping: map our logical model names to catalog llm_id values
# Defaults align to the catalog list provided; can be overridden via environment variables
DATAIKU_CATALOG_MAP = {
    # High-quality model mapping
    "gpt-4o": os.getenv("DATAIKU_LLM_GPT4O", "azureopenai:Azure-OpenAI-Prod:gpt-4o"),
    # Cost-effective/default fallback for 3.5 usage
    "gpt-3.5-turbo": os.getenv("DATAIKU_LLM_GPT35", "azureopenai:Azure-OpenAI-Prod:gpt-4o-mini"),
    # Optional additional mappings (available in catalog)
    "gpt-4.1": os.getenv("DATAIKU_LLM_GPT41", "azureopenai:Azure-OpenAI-Prod-4-1:gpt-4.1"),
    "gpt-4.1-mini": os.getenv("DATAIKU_LLM_GPT41_MINI", "azureopenai:Azure-OpenAI-Prod-4-1:gpt-4.1-mini"),
    "o4-mini": os.getenv("DATAIKU_LLM_O4_MINI", "azureopenai:Azure-OpenAI-Prod-4-1:o4-mini"),
    # GPT-5 model mapping - will work when IT deploys it in Dataiku
    "gpt-5": os.getenv("DATAIKU_LLM_GPT5", "azureopenai:Azure-OpenAI-Prod:gpt-5"),
}

# DEPRECATED: Embedding provider control (no longer used)
# Framework mapping now uses GPT-based reasoning instead of embeddings
# Keeping these for backwards compatibility but they have no effect
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gpt")  # Changed default from "openai" to "gpt"
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")  # Not used

# Toggle for control/CUEC framework mapping (now uses GPT instead of embeddings)
CONTROL_EMBEDDING_MAPPING_ENABLED = os.getenv("CONTROL_EMBEDDING_MAPPING_ENABLED", "true").lower() == "true"

# Multi-match framework mapping configuration
ENABLE_MULTI_MATCH_MAPPING = os.getenv("ENABLE_MULTI_MATCH_MAPPING", "false").lower() == "true"
FRAMEWORK_CATEGORY_SCORE_THRESHOLD = int(os.getenv("FRAMEWORK_CATEGORY_SCORE_THRESHOLD", "7"))
FRAMEWORK_MAX_CATEGORIES = int(os.getenv("FRAMEWORK_MAX_CATEGORIES", "2"))
FRAMEWORK_MAX_CRITERIA_PER_PASS = int(os.getenv("FRAMEWORK_MAX_CRITERIA_PER_PASS", "15"))

# Batch mapping endpoint configuration
MAX_BATCH_MAPPING_CONCURRENT = int(os.getenv("MAX_BATCH_MAPPING_CONCURRENT", "3"))
BATCH_MAPPING_BATCH_SIZE = int(os.getenv("BATCH_MAPPING_BATCH_SIZE", "10"))
BATCH_MAPPING_DEFAULT_THROTTLE_MS = int(os.getenv("BATCH_MAPPING_DEFAULT_THROTTLE_MS", "100"))
BATCH_MAPPING_ENABLE_AUTO_THROTTLE = os.getenv("BATCH_MAPPING_ENABLE_AUTO_THROTTLE", "true").lower() == "true"
BATCH_MAPPING_TARGET_CPU_PCT = int(os.getenv("BATCH_MAPPING_TARGET_CPU_PCT", "60"))

# TSC Anomaly Detection Configuration
# Base threshold for flagging TSC headings as anomalies (e.g., CC6.1 appearing 20+ times)
TSC_ANOMALY_BASE_THRESHOLD = int(os.getenv("TSC_ANOMALY_BASE_THRESHOLD", "20"))
# Enable adaptive threshold based on report size (10% of total controls)
TSC_ANOMALY_ADAPTIVE_ENABLED = os.getenv("TSC_ANOMALY_ADAPTIVE_ENABLED", "true").lower() == "true"
# Minimum threshold to prevent false positives in small reports
TSC_ANOMALY_MIN_THRESHOLD = int(os.getenv("TSC_ANOMALY_MIN_THRESHOLD", "5"))

# Control Merge Suggestions Configuration
# Minimum confidence score (0.0-1.0) to suggest merging duplicate controls
MERGE_SUGGESTION_MIN_CONFIDENCE = float(os.getenv("MERGE_SUGGESTION_MIN_CONFIDENCE", "0.50"))
# Maximum number of merge suggestions to return per request
MERGE_SUGGESTION_MAX_RESULTS = int(os.getenv("MERGE_SUGGESTION_MAX_RESULTS", "50"))

# Framework Preview Rate Limiting
# Maximum preview requests per scan per minute
FRAMEWORK_PREVIEW_RATE_LIMIT = int(os.getenv("FRAMEWORK_PREVIEW_RATE_LIMIT", "10"))

# Docker control (frontend UI) enable flag
DOCKER_CONTROL_ENABLED = os.getenv("DOCKER_CONTROL_ENABLED", "false").lower() == "true"

# --- Timeout configuration for external service calls ---
# DSS client operations (completions, embeddings); 0 means no timeout
DATAIKU_DSS_CALL_TIMEOUT = float(os.getenv("DATAIKU_DSS_CALL_TIMEOUT", "90"))
# Overall request timeout for HTTP-based providers (Azure, API Node); includes connect + read
HTTP_REQUEST_TIMEOUT = float(os.getenv("HTTP_REQUEST_TIMEOUT", "120"))

# --- Redis Configuration ---
REDIS_URL = os.environ.get("SOCANALYZER_REDIS_URL", "redis://localhost:6379/0")

# Project root (SOCAnalyzer5)
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
JSON_DIR = DATA_DIR / "json"
LOGS_DIR = DATA_DIR / "logs"
OUTPUT_DIR = DATA_DIR / "output"

# Canonical file paths
SECTION_JSON_PATH = JSON_DIR / "section_results.json"
PDF_TXT_PATH = OUTPUT_DIR / "output.txt"
CONTROL_JSON_PATH = JSON_DIR / "control_result.json"
CONTROL_GPT_LOG_PATH = LOGS_DIR / "control_gpt.log"
# Add other extractor output/log paths as needed

# Path to SOC reports
SOC2_REPORTS_DIR = PROJECT_ROOT / 'soc2_reports'

# Path to output text file (legacy, prefer PDF_TXT_PATH)
OUTPUT_TEXT_FILE = str(PDF_TXT_PATH)

# --- Analyzer/watchdog and timeouts (tunable) ---
# Group timeout for parallel extractors. 0 disables timeout (wait indefinitely).
PARALLEL_EXTRACTORS_TIMEOUT_SECONDS = int(os.getenv("PARALLEL_EXTRACTORS_TIMEOUT_SECONDS", "0"))
# Job-level watchdog: if progress stays at/above this percent for idle seconds, finalize from disk. 0 disables.
JOB_WATCHDOG_MIN_PROGRESS = int(os.getenv("JOB_WATCHDOG_MIN_PROGRESS", "95"))
JOB_WATCHDOG_IDLE_SECONDS = int(os.getenv("JOB_WATCHDOG_IDLE_SECONDS", "0"))
# Control extractor progress watchdog (used by analyze.py)
CONTROL_WATCHDOG_ENABLED = os.getenv("CONTROL_WATCHDOG_ENABLED", "true").lower() == "true"
CONTROL_WATCHDOG_MAX_MINUTES = int(os.getenv("CONTROL_WATCHDOG_MAX_MINUTES", "25"))

# --- Entity Extraction Configuration ---
MAX_SEARCH_OCCURRENCES = 3  # Warn user if more than this many occurrences found
ENTITY_EXTRACTION_TIMEOUT = 120  # Timeout in seconds for entity extraction endpoint

# --- GPT Prompts for Section Detection and TOC Parsing ---

SECTION_DETECTION_PROMPT = """
You are an expert SOC 2 document analyst. Identify the most probable start position for each requested section topic in the provided report text.

## Objective
For every topic in {section_keys}, return a single best-guess section start using character offsets in the exact input string {text}. Output a JSON array of objects with:
- topic: <string, the requested topic as provided>
- offset: <int, 0-based character index in {text}>
- percent: <float, (offset / len({text})) * 100, rounded to 3 decimals>
- confidence: <float 0–100, your probability that this is the correct start>

## Rules
1. Use only the provided text. Do not infer content that is not present.
2. Prefer the Table of Contents (if it appears early in {text}) to estimate a target page/position; then validate by scanning nearby content.
3. A valid section start must align with a heading-like line (title-cased, numbered, or visually distinct) or a clear semantic boundary immediately preceding the section's body.
4. Do NOT choose the first naive keyword hit. Validate that the surrounding lines look like a true section heading and that subsequent lines read like section content.
5. If multiple candidates exist, apply this tie-breaker order:
   (a) A TOC-referenced heading match (or close variant) at a plausible position,
   (b) Exact/near-exact heading on its own line,
   (c) Strong semantic boundary (e.g., preceding whitespace, numbering, or divider lines),
   (d) Earliest plausible location that satisfies the above.
6. Be tolerant of heading variants (e.g., punctuation, roman numerals, numbering, minor wording changes).
7. If no credible start is found for a topic, omit that topic from the output (do not fabricate a result).

## Computation Details
- offset: index of the first character of the heading line (or its immediate boundary) in {text}.
- percent: (offset / total_chars) * 100, where total_chars = len({text}); round to 3 decimals.
- confidence: calibrated probability (0–100) reflecting signal strength from TOC corroboration, heading quality, and local context coherence.

## Output
Respond with ONLY a valid JSON array (no prose, no markdown). Each element must include all four fields in the exact types specified above.

SOC Report Text:
{text}
"""

EXTRACT_TOC_PROMPT = """
You are an expert SOC 2 report analyst. Your goal is to extract only the Table of Contents (TOC) from the beginning portion of the provided report text.

## Rules
1. The TOC usually appears within the first few pages, often between "Contents" and the first major section heading.
2. Capture the entire TOC exactly as it appears — including page numbers, dots, and indentation.
3. Do not include any content before or after the TOC (e.g., disclaimers, titles, body sections).
4. If no TOC or partial TOC is found, respond only with the string: TOC NOT FOUND.
5. Do not summarize, interpret, or clean up the text.

## Output
Return the Table of Contents as plain text exactly as it appears.

Report Text:
{text}
"""

SECTION_HEADING_VALIDATION_PROMPT = """
You are validating whether a given line in a SOC 2 report looks like a section heading.

## Rules
1. Consider capitalization, formatting cues (numbered or roman numerals), indentation, and standalone line structure.
2. True headings are typically title-cased, may include numbering (e.g., "II. Description of System"), and are visually distinct from running text.
3. Lines that are full sentences, contain punctuation like commas or periods (beyond numbering), or run into adjacent text are not section headings.
4. Use the full context provided to make your decision.

## Output
Respond with one of:
- Yes – followed by a short reason (e.g., "Yes – centered title case on its own line")
- No – followed by a short reason (e.g., "No – appears as part of a paragraph")

Context:
{text}
>>> {line}
"""

EXTRACT_TOC_HEADINGS_AND_PAGES_PROMPT = """
You are parsing a Table of Contents extracted from a SOC 2 report.

## Task
Extract only MAIN section headings (not subsections or nested entries) and their corresponding page numbers.

## Rules
1. Ignore indented or obviously nested lines that represent subsections.
2. Capture only high-level entries that correspond to major report sections (e.g., Management Assertion, Service Auditor's Report, Description of System, etc.).
3. Return results as a JSON array of objects, each with:
   - "heading": <string, section title exactly as shown>
   - "page": <integer or string, page number if shown>
4. Do not include any commentary, markdown, or text outside the JSON array.

## Output Example
[
  {{"heading": "Section I – Assertion of Management", "page": 1}},
  {{"heading": "Section II – Service Auditor's Report", "page": 3}}
]

TOC:
{toc_text}
"""

# --- GPT Prompts for Extractors ---

# CUEC Extraction Prompt
CUEC_EXTRACTION_PROMPT = """
You are an expert SOC 2 auditor. Your task is to extract only **Complementary User Entity Controls (CUECs)** — statements that assign responsibilities to the user entity, customer, or client.

## Rules
1. A valid CUEC explicitly assigns responsibility to the user entity (e.g., "User entities must…", "Customers are responsible for…").
2. Do NOT include internal vendor controls, product descriptions, or general control statements that do not assign responsibility.
3. Ignore any statement where responsibility is assigned to {company_names} or {parent_company_names}.
4. For each valid CUEC, extract:
     - cuec_tsc_id: TSC ID if present, else null.
     - cuec_description: full CUEC statement.
     - cuec_line_ref: integer line number where found.
     - cuec_gpt_opinion: "Yes" (is a CUEC) or "No".
     - cuec_gpt_responsibility_phrase: exact responsibility phrase (e.g., "user entities are responsible for…"), or null if not clear.
     - cuec_gpt_reasoning: concise reasoning for inclusion.
     - cuec_framework_alignment: "COSO", "AICPA_TSC", "COSO or AICPA_TSC", or "Undetermined".
     - cuec_framework_alignment_id: COSO or AICPA TSC ID if determinable, else null.
     - cuec_justification: brief rationale for framework alignment.
5. For every non-CUEC control or statement reviewed, output an entry in a second array named "excluded" with:
     - excluded_description: the statement.
     - excluded_reason: short reason why it is not a CUEC.
6. Do not fabricate IDs or frameworks. Use null for missing data.
7. Return one JSON object containing two arrays: "cuecs" and "excluded".
8. No markdown, commentary, or text outside JSON.

## Output Example
{{
    "cuecs": [
        {{
            "cuec_tsc_id": "CC6.1",
            "cuec_description": "User entities must restrict access to their own credentials.",
            "cuec_line_ref": 1254,
            "cuec_gpt_opinion": "Yes",
            "cuec_gpt_responsibility_phrase": "User entities must",
            "cuec_gpt_reasoning": "Explicit customer responsibility language.",
            "cuec_framework_alignment": "AICPA_TSC",
            "cuec_framework_alignment_id": "CC6.1",
            "cuec_justification": "Relates to access control under TSC Security."
        }}
    ],
    "excluded": [
        {{"excluded_description": "The service provider maintains backups daily.", "excluded_reason": "Vendor responsibility, not user entity."}}
    ]
}}

SOC 2 Report Text:
{text}
"""

# CUEC Consolidation Prompt  
CUEC_CONSOLIDATION_PROMPT = """
You are an expert SOC 2 report analyst. Consolidate and deduplicate previously extracted CUECs.

## Objective
Merge similar or duplicate CUECs based on semantic similarity, description overlap, or identical TSC IDs.

## Rules
1. Combine entries that describe the same user responsibility, even if phrased slightly differently.
2. Preserve the most complete or representative description for each merged group.
3. Carry forward or average confidence indicators where applicable.
4. Include reasoning for each merge or retention decision.

## Output
Return a single JSON array (no wrapper object, no extra text).  
Each object must include:
{{
    "cuec_seq": <int>,
    "cuec_tsc_id": <string or null>,
    "cuec_description": <string>,
    "cuec_line_ref": <int or null>,
    "cuec_confidence": <float>,
    "cuec_gpt_opinion": <"Yes" or "No">,
    "cuec_distance_from_cuec_keywords": <int or null>,
    "cuec_gpt_reasoning": <string>,
    "cuec_framework_alignment": <string>,
    "cuec_framework_alignment_id": <string or null>,
    "cuec_justification": <string>
}}

Do not include commentary or markdown.

Extracted CUECs:
{cuecs}
"""

# Executive Summary Prompt
EXECUTIVE_SUMMARY_PROMPT = """
You are a senior risk analyst preparing a concise executive-level summary from SOC 2 report results.  
Generate an accurate, structured JSON summary covering the organization, findings, and recommendations.

## Scope
Inputs include SOC 2 coverage statistics, CUECs, COSO and TSC mapping tables, detected deviations, and SOX vendor status.

## Context
- **SOX Vendor Status**: {is_sox_vendor}
- If this is a SOX vendor (subject to Sarbanes-Oxley compliance), include specific assessments of:
  * SOX-relevant controls and their effectiveness
  * Financial reporting system controls
  * Access controls and segregation of duties
  * Change management and audit trail completeness
  * Any SOX compliance gaps or concerns

## Rules
1. Use provided variables — company='{company}', product='{product}', is_sox_vendor='{is_sox_vendor}' — when composing the about_company section.
2. **SOX-Specific Analysis**: If is_sox_vendor is True/Yes, dedicate at least one key finding and one recommendation specifically to SOX compliance implications.
3. **Coverage Analysis**: Explicitly mention TSC coverage percentage ({tsc_covered}/{tsc_total}) and COSO coverage percentage ({coso_covered}/{coso_total}).
4. **CUEC Analysis**: Analyze CUEC control strength assessments and identify:
   - CUECs marked as "Weak" or "Not Effective" - these are HIGH RISK
   - CUECs marked as "Adequate" or "Moderate" - these need monitoring
   - Gaps where CUECs have no control strength assessment
5. **Gap Analysis**: Identify and highlight:
   - Missing TSC criteria (uncovered items from table)
   - Missing COSO components (uncovered items from table)
   - CUECs without control strength ratings
   - Subservice organizations with inadequate controls
6. Treat any missing sections as "unknown/not covered" but do not list them as deficiencies unless they are SOX-relevant gaps.
7. Do not repeat input data; synthesize it into insights.
8. Every finding or recommendation must be plausible and customer-relevant (not advice for the vendor's internal controls).
9. Maintain neutral, audit-appropriate tone — no marketing language or speculation.
10. **SOX-Specific Sections**: If is_sox_vendor is True/Yes, include:
   - "sox_objective": Review objective statement
   - "sox_assessors_conclusion": Structured assessment with Adequacy, Operating Effectiveness, and Material Weaknesses subsections

## Output Format
Return only a valid JSON object. The structure depends on whether this is a SOX vendor:

### If is_sox_vendor is "Yes" or "True", you MUST include these additional fields:
{{
    "about_company": "<brief narrative about {company} and product {product}, with grade A/B/C/D. Mention if SOX vendor and implications.>",
    "sox_objective": "<REQUIRED for SOX vendors. Use this exact template: 'The objective of this review was to assess the effectiveness and reliability of the internal controls over protecting the security, confidentiality, integrity, and availability of the system responsible for {product} for Solidigm during the period {coverage_period}. This review was carried out in accordance with the agreed-upon procedures and standards established by the American Institute of Certified Public Accountants (AICPA).'>",
    "key_findings": ["<1–2 sentences each. Include TSC/COSO coverage stats, CUEC control strength summary, deviations count, and SOX implications.>"],
    "areas_of_concern": ["<1–2 sentences each. Focus on weak CUECs, coverage gaps, deviations, and SOX gaps.>"],
    "sox_assessors_conclusion": {{
        "adequacy": "<REQUIRED for SOX vendors. Assess the adequacy of control coverage for SOX compliance. Address whether controls are sufficient in design to meet financial reporting and security requirements. Be specific about what is adequate and what is not.>",
        "operating_effectiveness": "<REQUIRED for SOX vendors. Provide conclusions about operating effectiveness. If deficiencies were found, explicitly state them and their impact on SOX compliance. If no deficiencies, state that clearly.>",
        "material_weaknesses": "<REQUIRED for SOX vendors. Identify any gaps that would SIGNIFICANTLY impact integrity, availability, confidentiality, and security RELEVANT TO SOLIDIGM. If none found, state exactly: 'No material weaknesses identified that would significantly impact Solidigm operations.'>"
    }},
    "deviations_noted": [
        {{"control_id": "<string>", "deviation_summary": "<concise issue description>"}}
    ],
    "unknown_coverage_gaps": ["<List missing TSC/COSO criteria, CUECs without control strength, not tested items.>"],
    "recommendations_risk_mitigations": ["<up to 3 actionable technical/operational recommendations. Prioritize weak CUEC controls and SOX gaps.>"],
    "recommendations_contract_enhancements": ["<up to 3 actionable contractual/DPA/SLA recommendations. Include CUEC control requirements and SOX attestations.>"],
    "recommendations": ["<union of all recommendations above>"]
}}

### If is_sox_vendor is "No" or "False", use this structure (omit sox_objective and sox_assessors_conclusion):
{{
    "about_company": "<brief narrative about {company} and product {product}, with grade A/B/C/D.>",
    "key_findings": ["<1–2 sentences each. Include TSC/COSO coverage stats, CUEC control strength summary, deviations count.>"],
    "areas_of_concern": ["<1–2 sentences each. Focus on weak CUECs, coverage gaps, deviations.>"],
    "deviations_noted": [
        {{"control_id": "<string>", "deviation_summary": "<concise issue description>"}}
    ],
    "unknown_coverage_gaps": ["<List missing TSC/COSO criteria, CUECs without control strength, not tested items.>"],
    "recommendations_risk_mitigations": ["<up to 3 actionable technical/operational recommendations.>"],
    "recommendations_contract_enhancements": ["<up to 3 actionable contractual/DPA/SLA recommendations.>"],
    "recommendations": ["<union of all recommendations above>"]
}}

## Inputs
SOC 2 Executive Summary Stats:
- Subservice orgs: {suborg_count}
- CUECs: {cuec_count}
- TSC coverage: {tsc_covered} of {tsc_total}
- COSO coverage: {coso_covered} of {coso_total}

TSC Table:
{tsc_table}

COSO Table:
{coso_table}

Detected Deviations:
{detected_deviations}

Control Test Results:
{control_test_results}

CUEC Control Strength Assessments:
{cuec_control_strengths}
"""

# Prompt for extracting the auditor firm from the auditor section
AUDITOR_EXTRACTION_PROMPT = """
You are an expert SOC 2 report analyst. Your task is to identify the *independent auditing firm* that conducted the SOC 2 examination.

## Rules
1. Analyze only the provided text, which comes from the Service Auditor’s Report section (and possibly the first page of the report).
2. Look specifically for the independent service auditor’s firm name—commonly appearing near phrases such as:
     - “Independent Service Auditor’s Report”
     - “performed by”, “issued by”, or “examined by”
     - firm signatures or letterheads (e.g., Deloitte, EY, PwC, KPMG, Schellman)
3. Do **not** return the company being audited, its parent, or affiliates as the auditor.
4. If multiple firms are mentioned, choose the one most clearly identified as the *service auditor*.
5. If the text does not clearly contain the auditor name, return null values instead of guessing.
6. Always provide a brief explanation describing how you identified or ruled out the auditor.

## Output Format
Respond **only** with a valid JSON object using this exact structure:

{{
    "auditor": "<string | null>",
    "confidence": <float between 0 and 1>,
    "explanation": "<string (one concise sentence explaining your reasoning)>"
}}

## Input
Text:
{text}
"""

# Enhanced prompt for auditor extraction, excluding company and parent company
AUDITOR_EXTRACTION_PROMPT_EXCLUDE = """
You are an expert SOC 2 auditor. Identify the independent **auditing firm** that performed the SOC 2 examination.

## Context
- The text comes from the Service Auditor’s Report section or report front matter.
- May also be found near auditor signatures or opinion language or headers or footers.
- The audited company and its parent (if any) are usually provided below:
    {company_line}

## Rules
1. Extract only the independent **service auditor firm name** (e.g., Deloitte, EY, PwC, KPMG, Schellman).
2. Exclude:
     - The company being audited.
     - Any parent/owner company.
     - References to subservice organizations or software vendors.
3. Look near headings such as “Independent Service Auditor’s Report,” auditor signatures, or opinion language.
4. If multiple firms are mentioned, choose the one explicitly responsible for the SOC 2 examination.
5. If not found, set auditor = null and confidence = 0. DO NOT guess.
6. Provide a one-sentence explanation of how you determined or ruled out the auditor.

## Output
Return one JSON object:
{{
    "auditor": "<string | null>",
    "confidence": <float 0–1>,
    "explanation": "<string>"
}}

SOC 2 Report Text:
{text}
"""

# Retry prompt for auditor extraction with enhanced validation instructions
AUDITOR_EXTRACTION_PROMPT_RETRY = """
You are an expert SOC 2 auditor. Identify the independent **auditing firm** that performed the SOC 2 examination.

## Context
- The text comes from the Service Auditor's Report section or report front matter.
- May also be found near auditor signatures or opinion language or headers or footers.
- The audited company and its parent (if any) are usually provided below:
    {company_line}

## Rules
1. Extract only the independent **service auditor firm name** (e.g., Deloitte, EY, PwC, KPMG, Schellman).
2. Exclude:
     - The company being audited.
     - Any parent/owner company.
     - References to subservice organizations or software vendors.
3. Look near headings such as "Independent Service Auditor's Report," auditor signatures, or opinion language.
4. If multiple firms are mentioned, choose the one explicitly responsible for the SOC 2 examination.
5. If not found, set auditor = null and confidence = 0. DO NOT guess.
6. Provide a one-sentence explanation of how you determined or ruled out the auditor.

## CRITICAL VALIDATION REQUIREMENT
**You must extract the auditor name EXACTLY as it appears in the text.**
- Do NOT paraphrase, abbreviate, or use variations.
- Copy the exact text string character-for-character.
- If you cannot find an auditor firm name that appears verbatim in the text, set auditor = null.

## Output
Return one JSON object:
{{
    "auditor": "<string | null>",
    "confidence": <float 0–1>,
    "explanation": "<string>"
}}

SOC 2 Report Text:
{text}
"""

# Two-stage auditor extraction prompts
AUDITOR_COMPANY_EXTRACTION_PROMPT = """
You are an expert SOC 2 report analyst. Extract ALL company names, firm names, and organization names mentioned in this text.

## Context
- This text comes from a SOC 2 examination report (pages 1-3 and/or Service Auditor's Report section)
- Look for companies near:
  - "Independent Service Auditor's Report" headings
  - Headers and footers on each page
  - Auditor signatures and letterheads
  - Opinion statements and examination language
  - Company descriptions and service provider mentions

## Task
Extract EVERY company, firm, or organization name you find. Include:
- Audit firms (CPA firms like Deloitte, KPMG, etc.)
- The company being audited (service provider)
- Parent companies
- Subservice organizations
- Any other companies mentioned

## Output Format
Return ONLY a JSON array of company names as strings:
["Company Name 1", "Company Name 2", "Company Name 3", ...]

If you find no company names, return: []

## Important
- Extract the full legal name as it appears (e.g., "BDO USA, P.C." not "BDO")
- Include all variations you find (we will deduplicate later)
- Do NOT filter or exclude any companies at this stage

TEXT:
{text}
"""

AUDITOR_IDENTIFICATION_PROMPT = """
You are an expert SOC 2 auditor. Identify which company from the provided list is the independent auditing firm that performed the SOC 2 examination.

## Context
{company_line}

## Companies Found in Report
The following companies were extracted from the report text:
{companies}

## Task
Identify which ONE company is the independent service auditor (CPA firm) that conducted the SOC 2 examination.

## Reasoning Guidelines
Consider:
1. **Industry knowledge**: Which companies are known SOC 2 audit firms? (Big 4: Deloitte, PwC, KPMG, EY; Top regional: BDO, RSM, Grant Thornton, Schellman, etc.)
2. **Context clues**: Which company appears near "Independent Service Auditor's Report", "examined", "performed by", opinion language?
3. **Naming patterns**: CPA firms often include "LLP", "LLC", "P.C.", "& Company", "Assurance" in their legal names
4. **Exclusions**: Do NOT select the company being audited, parent companies, or subservice organizations

## Output Format
Return ONLY a JSON object with this exact structure:
{{
    "auditor": "<full legal name of audit firm or null>",
    "confidence": <float between 0.0 and 1.0>,
    "reasoning": "<2-3 sentence explanation of how you identified the auditor based on context clues, industry knowledge, and naming patterns>"
}}

If you cannot confidently identify the auditor, set auditor=null and confidence=0.0.
"""

# Prompt for extracting the company being audited and any parent company
COMPANY_EXTRACTION_PROMPT = """
You are an expert SOC 2 report analyst. Extract the company (legal entity) being audited, and any parent or owner company mentioned.

## Rules
1. Look for explicit entity names in the management assertion, title page, or system description (e.g., “XYZ Corp. (an ABC Company)”).
2. Always extract the company being audited. Parent/owner is optional if clearly stated.
3. Ignore auditor names, subservice orgs, and references to unrelated parties.
4. If the company or parent cannot be determined, set those fields to null.
5. Provide a confidence score (0–1) and a one-sentence explanation.

## Output
Return one JSON object:
{{
    "company": "<string | null>",
    "parent_company": "<string | null>",
    "confidence": <float 0–1>,
    "explanation": "<string, concise reasoning>"
}}

SOC 2 Report Text:
{text}
"""

# Prompt for extracting the product/service/system being audited
PRODUCT_EXTRACTION_PROMPT = """
You are an expert SOC 2 systems auditor. Extract the **product, service, or system** that is in scope for the SOC 2 examination.

## Rules
1. Identify the specific platform, service, or product name being audited (e.g., “Okta Identity as a Service”, “Experience Cloud”).
2. Prefer explicit scope statements (e.g., “system description covers…” or “controls relevant to…”).
3. Exclude company names, parent organizations, and general descriptive phrases.
4. If not clearly stated, set product = null and confidence = 0.
5. Provide a confidence score and brief explanation.

## Output
Return one JSON object:
{{
    "product": "<string | null>",
    "confidence": <float 0–1>,
    "explanation": "<string>"
}}

SOC 2 Report Text:
{text}
"""

# Prompt for extracting the report date
REPORT_DATE_EXTRACTION_PROMPT = """
You are an expert SOC 2 auditor. Extract the **report signing date** (the date the auditor signed the opinion).

## Rules
1. Focus on the end of the Service Auditor’s Report section, near the signature block.
2. Identify the most recent complete date (e.g., “June 30, 2024”) and convert it to ISO format (YYYY-MM-DD) when possible.
3. Ignore coverage period dates and fieldwork references.
4. If no date is found, set report_date = null.
5. Always include a short explanation.

## Output
{{
    "report_date": "<YYYY-MM-DD | null>",
    "explanation": "<string>"
}}

SOC 2 Report Text:
{text}
"""

# Prompt for extracting the coverage period
COVERAGE_PERIOD_EXTRACTION_PROMPT = """
You are an expert SOC 2 auditor. Determine the **coverage period** and report type (Type 1 or Type 2) from the given text.

## Rules
1. A Type 2 report includes both start and end dates (period of review).
2. A Type 1 report includes only a single “as-of” date — treat that as end_date and set start_date = null.
3. Use ISO format (YYYY-MM-DD) for all dates when possible.
4. Include an explanation describing how you identified the report type and dates.
5. If the period cannot be determined, set both dates to null.

## Output
{{
    "type": "<Type 1 | Type 2>",
    "start_date": "<YYYY-MM-DD | null>",
    "end_date": "<YYYY-MM-DD | null>",
    "as_of_date": "<YYYY-MM-DD | null>",
    "explanation": "<string>"
}}

Report Text:
{text}
"""


# Path to .env file for API key
ENV_PATH = str(PROJECT_ROOT / '.env')

# Default model to use
DEFAULT_GPT_MODEL = os.getenv('DEFAULT_GPT_MODEL', 'gpt-4o')

# Default generation parameters
DEFAULT_TEMPERATURE = float(os.getenv('DEFAULT_TEMPERATURE', '0.0'))
DEFAULT_TOP_P = float(os.getenv('DEFAULT_TOP_P', '0.0'))  # 0.0 for determinism
# --- Control extractor consistency tuning ---
# Reduce variability by disabling aggressive non-control detection and GPT-based next-start verification
CONTROL_DETECT_NON_CONTROL_CONTENT = False
CONTROL_VERIFY_NEXT_START_ENABLED = False


# --- Advanced GPT Token & Chunk Management ---
# Character-per-token heuristic; make env configurable and slightly conservative for English prose.
CHARS_PER_TOKEN = float(os.getenv('CHARS_PER_TOKEN', '4.0'))

# Model-aware context window sizes with env overrides
_CTX_GPT5 = int(os.getenv('GPT5_CONTEXT_TOKENS', '128000'))
_CTX_GPT4O = int(os.getenv('GPT4O_CONTEXT_TOKENS', '128000'))
_CTX_GPT41 = int(os.getenv('GPT41_CONTEXT_TOKENS', '128000'))
_CTX_GPT35 = int(os.getenv('GPT35_CONTEXT_TOKENS', '16000'))

LOGICAL_MODEL_CONTEXT = {
    'gpt-5': _CTX_GPT5,
    'gpt-4o': _CTX_GPT4O,
    'gpt-4.1': _CTX_GPT41,
    'gpt-3.5-turbo': _CTX_GPT35,
}

# Resolve context window from DEFAULT_GPT_MODEL; fall back to a safe large window
MAX_TOTAL_TOKENS = LOGICAL_MODEL_CONTEXT.get(DEFAULT_GPT_MODEL, _CTX_GPT4O)

# Token Management (env overridable)
MAX_OUTPUT_TOKENS = int(os.getenv('MAX_OUTPUT_TOKENS', '2000'))
MAX_INPUT_TOKENS = MAX_TOTAL_TOKENS - MAX_OUTPUT_TOKENS

# Token Budget Allocations (these are logical planning budgets, not hard API limits)
GPT_SYSTEM_TOKENS = int(os.getenv('GPT_SYSTEM_TOKENS', '400'))
GPT_USER_TOKENS = int(os.getenv('GPT_USER_TOKENS', '400'))
GPT_RESPONSE_TOKENS = int(os.getenv('GPT_RESPONSE_TOKENS', '500'))
GPT_AVAILABLE_TOKENS = (
    MAX_TOTAL_TOKENS
    - GPT_SYSTEM_TOKENS
    - GPT_USER_TOKENS
    - GPT_RESPONSE_TOKENS
)

# Content Chunking Strategy (derived from budgets)
DEFAULT_CHUNK_SIZE = int(GPT_AVAILABLE_TOKENS * CHARS_PER_TOKEN * 0.40)  # ~40% of available space
PRIMARY_CHUNK_SIZE = int(GPT_AVAILABLE_TOKENS * CHARS_PER_TOKEN * 0.60)  # ~60% for critical fields
DESCRIPTION_CHUNK_SIZE = int(GPT_AVAILABLE_TOKENS * CHARS_PER_TOKEN * 0.40)
SUBSERVICE_CHUNK_SIZE = int(GPT_AVAILABLE_TOKENS * CHARS_PER_TOKEN * 0.30)
MAX_CHUNK_SIZE = int(MAX_INPUT_TOKENS * CHARS_PER_TOKEN * 0.80)  # 80% of max input tokens for safety

# Executive Summary input budgeting (character-based) to avoid context overruns
EXEC_SUMMARY_TEST_RESULTS_BUDGET_CHARS = int(MAX_INPUT_TOKENS * CHARS_PER_TOKEN * 0.45)  # ~45% of input budget
EXEC_SUMMARY_PER_CONTROL_MAX_CHARS = int(os.getenv('EXEC_SUMMARY_PER_CONTROL_MAX_CHARS', '700'))
EXEC_SUMMARY_MAX_NON_DEVIATION_CONTROLS = int(os.getenv('EXEC_SUMMARY_MAX_NON_DEVIATION_CONTROLS', '60'))
EXEC_SUMMARY_TOKEN_WARNING_THRESHOLD = float(os.getenv('EXEC_SUMMARY_TOKEN_WARNING_THRESHOLD', '0.90'))  # Warn at 90% of token limit

# Total Combined Text Limits
TOTAL_PRIMARY_SIZE = PRIMARY_CHUNK_SIZE * 3  # Allow for multiple primary sections
TOTAL_DESCRIPTION_SIZE = DESCRIPTION_CHUNK_SIZE * 3  # Allow for multiple description sections
# Overlap: default to 10% of primary chunk, min 200 chars; env overridable
TEXT_OVERLAP = int(os.getenv('TEXT_OVERLAP', str(max(200, int(PRIMARY_CHUNK_SIZE * 0.10)))))

# Configuration for GPT models - uses DEFAULT_GPT_MODEL unless specifically overridden
GPT_MODELS = {
    'control_extractor_v2': DEFAULT_GPT_MODEL,
    'company_extractor': DEFAULT_GPT_MODEL,
    'auditor_extractor': DEFAULT_GPT_MODEL,
    'product_extractor': DEFAULT_GPT_MODEL,
    'report_date_extractor': DEFAULT_GPT_MODEL,
    'coverage_period_extractor': DEFAULT_GPT_MODEL,
    'cuec_extractor': DEFAULT_GPT_MODEL,
    'subservice_orgs_extractor': DEFAULT_GPT_MODEL,
    'subservice_orgs_gpt_verify': DEFAULT_GPT_MODEL,
    'executive_summary': DEFAULT_GPT_MODEL,
}

SECTION_TOPICS = {
    "Management_Assertion": [
        "Assertion of Management", "Management Assertion", "Management's Assertion", "product that was in scope", "company name that was audited", "Assertion of [COMPANY] Management"
    ],
    "Service_Auditor_Report": [
        "Independent Service Auditor's Report", "Independent Service Auditor's Report on a SOC Examination", "Independent Service Auditor's Assurance Report",
        "Auditor Report", "Auditor's Report", "Independent Auditor Report", "Service Auditor Report", "Service Auditor's Report", "Independent Service Auditor", "Auditor's Report"
    ],
    "Description_of_System": [
        "Description of the System", "system description", "description of system", "[COMPANY] Description of System"
    ],
    "Control_Descriptions": [
        "Testing Matrices", "Trust Services Criteria Related Controls Tests of Controls", "Trust Services Criteria", "Service Auditor's Test of Controls", "Test Results",
        "Trust Services Criteria", "Testing Matrices"
    ]
}

# SOC 1 Section Patterns (ICFR focus)
SECTION_TOPICS_SOC1 = {
    "Management_Assertion": [
        "Assertion of Management", "Management Assertion", "Management's Assertion", "Management's Description and Assertion",
        "Management's Report", "Management Representation"
    ],
    "Service_Auditor_Report": [
        "Independent Service Auditor's Report", "Independent Accountant's Report", "Report of Independent Auditors",
        "Service Auditor's Report", "Auditor's Report on Controls", "Report on Controls at a Service Organization"
    ],
    "Description_of_Controls": [
        "Description of Controls", "Description of the Service Organization's System", "Service Organization's Description",
        "Description of [COMPANY] Controls", "System Description"
    ],
    "Control_Descriptions": [
        "Control Objectives and Related Controls", "Tests of Controls", "Control Testing", "Test of Operating Effectiveness",
        "Control Objectives", "Description of Tests", "Testing Results", "Service Organization's Controls"
    ],
    "CUEC_Section": [
        "Complementary User Entity Controls", "User Entity Controls", "Complementary Controls", "User Control Considerations",
        "Responsibilities of User Entities", "User Organization Controls"
    ]
}

# Combined Report Section Patterns (SOC 1 + SOC 2)
SECTION_TOPICS_COMBINED = {
    "Management_Assertion": [
        "Assertion of Management", "Management Assertion", "Management's Assertion", "Management's Description and Assertion"
    ],
    "Service_Auditor_Report": [
        "Independent Service Auditor's Report", "Independent Accountant's Report", "Service Auditor's Report"
    ],
    "Description_of_System": [
        "Description of the System", "Description of Controls", "Service Organization's Description", "System Description"
    ],
    "Control_Descriptions": [
        "Trust Services Criteria Related Controls", "Control Objectives and Related Controls", "Tests of Controls",
        "Testing Matrices", "Test Results", "Control Testing"
    ],
    "CUEC_Section": [
        "Complementary User Entity Controls", "User Entity Controls", "User Control Considerations"
    ]
}

# Priority keywords for section topic mapping
PRIORITY_KEYWORDS_MANAGEMENT_ASSERTION = [
    "assertion", "management assertion", "assertion of management", "assertion of [company] management"
]
PRIORITY_KEYWORDS_SERVICE_AUDITOR_REPORT = [
    "auditor report", "auditor's report", "independent auditor", "service auditor", "independent service auditor", "assurance report"
]
PRIORITY_KEYWORDS_DESCRIPTION_OF_SYSTEM = [
    "description", "system description", "description of system", "[company] description of system"
]
PRIORITY_KEYWORDS_CONTROL_DESCRIPTIONS = [
    "tests of controls", "test of controls", "testing of controls", "trust services criteria", "testing matrices", "test results"
]

WATERMARK_PATTERNS = [
    r"digitally signed by"
]

REGEX_PATTERNS = {
    'date': r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4})\b",
    'email': r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    'time': r"\b\d{1,2}:\d{2}(?::\d{2})?\s?(?:AM|PM|am|pm)?\b"
}

# Fuzzy score thresholds for section heading matching
FUZZY_SCORE_THRESHOLD_MAIN = 92  # Default for main topics
FUZZY_SCORE_THRESHOLD_OTHER = 85  # Default for other topics

# --- Subservice Org Extraction/Filtering Config ---
HEURISTIC_EXCLUDE_KEYWORDS = [
    'framework', 'operating system', 'standard', 'library', 'project', 'distribution', 'kernel', 'open source',
    'node', 'container', 'image', 'instance', 'os', 'component', 'platform', 'software', 'tool', 'plugin', 'module',
    'American Institute of Certified Public Accountants', 'American Institute of Certified Public Accountants (AICPA)',
    'AICPA', 'AICPA SOC 2', 'AICPA SOC 2 Report', 'AICPA SOC 2 Report on a SOC Examination', 'AICPA SOC 2 Report on a SOC Examination on a SOC Examination',
    'trusted certificate authority (CA)', 'trusted certificate authority', 'certificate authority (CA)', 'certificate authority',
    'independent auditor', 'independent auditor report', 'independent auditor report on a SOC examination', 'independent auditor report on a SOC examination on a SOC examination',
    'independent service auditor', 'independent service auditor report', 'independent service auditor report on a SOC examination', 'independent service auditor report on a SOC examination on a SOC examination',
    'Institute of Internal Auditors', 'Institute of Internal Auditors (IIA)', 'IIA', 'IIA SOC 2', 'IIA SOC 2 Report', 'IIA SOC 2 Report on a SOC Examination', 'IIA SOC 2 Report on a SOC Examination on a SOC Examination',
    'International Organization for Standardization', 'International Organization for Standardization (ISO)', 'ISO', 'ISO SOC 2', 'ISO SOC 2 Report', 'ISO SOC 2 Report on a SOC Examination', 'ISO SOC 2 Report on a SOC Examination on a SOC Examination',
    'International Organization for Standardization (ISO)', 'ISO', 'ISO SOC 2', 'ISO SOC 2 Report', 'ISO SOC 2 Report on a SOC Examination', 'ISO SOC 2 Report on a SOC Examination on a SOC Examination',
    'International Organization for Standardization (ISO)', 'ISO', 'ISO SOC 2', 'ISO SOC 2 Report', 'ISO SOC 2 Report on a SOC Examination', 'ISO SOC 2 Report on a SOC Examination on a SOC Examination',
    # Expanded generic/genericized terms
    'third-party specialist', 'third party specialist', 'specialist', 'consultant', 'contractor', 'team', 'group',
    'staff', 'employee', 'personnel', 'resource', 'service', 'support', 'department', 'division', 'unit', 'office',
    'committee', 'board', 'agency', 'organization', 'org', 'entity', 'provider', 'vendor', 'supplier', 'partner',
    'outsourcer', 'outsourcing', 'affiliate', 'subsidiary', 'internal', 'external', 'party', 'parties', 'individual',
    'role', 'function', 'subject', 'category', 'type', 'system', 'infrastructure', 'environment', 'solution',
    'process', 'procedure', 'practice', 'policy', 'program', 'initiative', 'activity', 'operation', 'operations',
    'network', 'site', 'location', 'facility', 'facilities', 'asset', 'assets', 'application', 'applications',
    'platforms', 'technologies', 'technology', 'hardware', 'cloud', 'cloud service', 'cloud provider', 'cloud platform',
    'managed service', 'managed services', 'hosting', 'host', 'maintenance', 'support team', 'support staff',
    'security team', 'it team', 'development team', 'engineering team', 'compliance team', 'audit team',
    'risk team', 'management team', 'leadership team', 'executive team', 'board of directors', 'committee',
    'task force', 'working group', 'advisory group', 'review group', 'review team', 'review board',
    'review committee', 'review panel', 'review body', 'review entity', 'review organization', 'review org',
    'review provider', 'review vendor', 'review supplier', 'review partner', 'review outsourcer', 'review affiliate',
    'review subsidiary', 'review internal', 'review external', 'review party', 'review parties', 'review individual',
    'review role', 'review function', 'review subject', 'review category', 'review type', 'review system',
    'review infrastructure', 'review environment', 'review solution', 'review process', 'review procedure',
    'review practice', 'review policy', 'review program', 'review initiative', 'review activity', 'review operation',
    'review operations', 'review network', 'review site', 'review location', 'review facility', 'review facilities',
    'review asset', 'review assets', 'review application', 'review applications', 'review platforms', 'review technologies',
    'review technology', 'review hardware', 'review cloud', 'review cloud service', 'review cloud provider',
    'review cloud platform', 'review managed service', 'review managed services', 'review hosting', 'review host',
    'review maintenance', 'review support team', 'review support staff', 'review security team', 'review it team',
    'review development team', 'review engineering team', 'review compliance team', 'review audit team',
    'review risk team', 'review management team', 'review leadership team', 'review executive team', 'review board of directors'
]

THIRD_PARTY_ALIAS_MAP = {
    'aws': 'Amazon Web Services',
    'amazon web services': 'Amazon Web Services',
    'amazon web services (aws)': 'Amazon Web Services',
    'aws (amazon web services)': 'Amazon Web Services',
    'amazon': 'Amazon Web Services',
    'amazon aws': 'Amazon Web Services',
    'microsoft azure': 'Microsoft Azure',
    'azure': 'Microsoft Azure',
    'azure (microsoft azure)': 'Microsoft Azure',
    'microsoft azure (azure)': 'Microsoft Azure',
    'gcp': 'Google Cloud Platform',
    'google cloud platform': 'Google Cloud Platform',
    'google cloud': 'Google Cloud Platform',
    'google cloud platform (gcp)': 'Google Cloud Platform',
    'gcp (google cloud platform)': 'Google Cloud Platform',
    'ibm cloud': 'IBM Cloud',
    'ibm': 'IBM Cloud',
    'oracle cloud': 'Oracle Cloud',
    'oracle': 'Oracle Cloud',
    'oci': 'Oracle Cloud',
    'oci (oracle cloud)': 'Oracle Cloud',
    'oracle cloud infrastructure': 'Oracle Cloud',
    'salesforce': 'Salesforce',
    'salesforce.com': 'Salesforce',
    'workday': 'Workday',
    'servicenow': 'ServiceNow',
    'service now': 'ServiceNow',
    'box': 'Box',
    'dropbox': 'Dropbox',
    'zendesk': 'Zendesk',
    'atlassian': 'Atlassian',
    'jira': 'Atlassian',
    'confluence': 'Atlassian',
    'slack': 'Slack',
    'github': 'GitHub',
    'gitlab': 'GitLab',
    'bitbucket': 'Bitbucket',
    'okta': 'Okta',
    'okta, inc.': 'Okta',
    'okta inc': 'Okta',
    'okta inc.': 'Okta',
    'microsoft': 'Microsoft Azure',
    'microsoft corporation': 'Microsoft Azure',
    'microsoft cloud': 'Microsoft Azure',
    'microsoft cloud (azure)': 'Microsoft Azure',
    # ... add more as needed ...
}

SO_KEYWORDS = ["subservice", "subservice organization"]

SUBSERVICE_ORG_ADVANCED_EXTRACTION_PROMPT = """
You are a SOC 2 report analysis expert. Your goal is to extract all third-party service providers (subservice organizations) mentioned in the provided text.

## Objective
Identify each third party referenced in the “Description of System” or similar section.  
For each, provide clear context about what they do and how they relate to the system.

## Rules
1. Include only **true third-party companies or service providers** (e.g., AWS, Azure, Google Cloud, Okta, Salesforce).
2. Exclude:
     - Internal teams, departments, or personnel.
     - Frameworks, standards, or open-source tools (e.g., NIST, ISO, Kubernetes, Linux).
     - Generic nouns (“vendor,” “service,” “consultant,” “support team,” etc.).
     - Subcomponents within known cloud platforms.
3. Use external knowledge *only for general recognition* of company functions (e.g., “Amazon Web Services – cloud hosting provider”).
4. Provide the following fields for each valid entity:
     - third_party_name
     - third_party_description
     - third_party_page_ref
     - third_party_confidence (float 0–1)
     - distance_from_so_keywords (integer distance from “subservice” keywords)
     - likely_so (“Yes” or “No”)
     - common_so (“Yes” or “No”)
     - third_party_controls: array of objects, each containing:
             - third_party_control_seq
             - third_party_control_id (string or null)
             - third_party_control_desc (string or null)
5. If no valid subservice organizations are found, return an empty JSON array.
6. Output only a valid JSON array (no commentary, markdown, or text).

SOC 2 Report Text:
{text}
"""

SUBSERVICE_ORG_GPT_FILTER_PROMPT = """
You are a SOC 2 domain expert verifying whether an extracted entity is a legitimate subservice organization.

## Task
Evaluate the following extracted entry and determine if it represents a **true external service provider** or something else.

## Rules
1. Keep only entities that provide a distinct external service or platform (e.g., AWS, Azure, Salesforce).
2. Exclude entries that are:
     - Frameworks, standards, operating systems, software, tools, or code libraries.
     - Departments, job titles, internal teams, or descriptive terms.
3. Identify the type of excluded entity precisely (e.g., OS, framework, internal team, generic term).
4. Return reasoning that explains why the entity is or isn’t a valid subservice organization.

## Output
Return a single JSON object:
{{
    "keep": <true or false>,
    "type": "<company/framework/software/OS/component/etc.>",
    "reason": "<brief justification>",
    "entry": <original entry as provided>
}}

Context from SOC 2 Report:
{context}

Entity to Evaluate:
Name: {name}
Description: {desc}
"""

SUBSERVICE_ORG_GPT_VERIFY_PROMPT = """
You are a SOC 2 compliance specialist. Determine whether the provided entity is a likely **subservice organization** referenced in a SOC 2 report.

## Rules
1. A subservice organization is an **external company** that performs part of the in-scope services or supports system operations (e.g., hosting, infrastructure, authentication).
2. Common examples: AWS, Azure, GCP, Google Cloud, Okta. 
3. Exclude internal teams, departments, frameworks, generic software, and most SaaS/monitoring/business tools.
4. Do NOT classify monitoring/logging/ticketing/alerting/HR/business/ITSM tools (e.g., Splunk, SolarWinds, ServiceNow, Workday, PagerDuty, Datadog, New Relic, Nagios, Jira, Grafana, Prometheus) as subservice organizations unless the context clearly shows they provide core system operations or hosting.
5. Be conservative — only mark true if the entity clearly fits SOC 2 subservice organization criteria and is not just a supporting SaaS tool.
6. Use the context and description to justify your decision.

## Output
Return a single JSON object:
{{
    "is_likely_subservice_org": <true or false>,
    "reason": "<brief justification>"
}}

Entity:
Name: {name}
Description: {desc}
"""

# GPT prompt to classify whether an entity is a known service provider
SUBSERVICE_ORG_SERVICE_PROVIDER_RESEARCH_PROMPT = """
You are a SOC 2 compliance and IT infrastructure expert. Determine whether the provided entity is a known infrastructure, cloud, colocation, or managed service provider that would typically be referenced as a subservice organization in a SOC 2 report.

## Service Provider Categories to Identify:
1. **Cloud/IaaS Providers**: AWS, Azure, GCP, Oracle Cloud, IBM Cloud, Alibaba Cloud, etc.
2. **Colocation/Data Center**: Equinix, Digital Realty, Cyxtera, NTT, CoreSite, QTS, Switch, Iron Mountain, etc.
3. **CDN/Edge**: Cloudflare, Akamai, Fastly, etc.
4. **Managed Hosting**: Rackspace, Liquid Web, etc.
5. **Network/Connectivity**: CenturyLink/Lumen, Verizon, AT&T, Level 3, Zayo, etc.
6. **Authentication/IAM Services** (when providing core identity infrastructure): Okta, Auth0, Ping Identity, etc.

## Exclusions:
- SaaS business applications (Salesforce, Workday, ServiceNow, SAP, Oracle apps)
- Monitoring/logging/ticketing tools (Splunk, Datadog, New Relic, PagerDuty, Jira)
- Productivity/collaboration tools (Slack, Microsoft 365, Google Workspace)
- Security tools (unless providing managed infrastructure services)

## Rules:
1. Use your knowledge of the IT industry to classify the entity
2. Consider the entity name and description provided
3. Be conservative - only mark as service provider if it clearly fits the categories above
4. Focus on entities that provide INFRASTRUCTURE or PLATFORM services, not software applications

## Output:
Return a single JSON object:
{{
    "is_service_provider": <true or false>,
    "provider_type": "<cloud|colocation|cdn|hosting|network|identity|unknown>",
    "confidence": <float 0.0-1.0>,
    "reason": "<brief justification>"
}}

Entity to Evaluate:
Name: {name}
Description: {desc}
"""

# Prompt used by the intelligent deduplication logic (subservice_orgs_dedup.py)
# Expects a JSON array string inserted as {json_data}. Returns a JSON object with a
# top-level "groups" array. Each group should include canonical_name, variations[],
# and a short reason explaining why they should be merged.
DEDUPLICATION_PROMPT = """
You are an expert data engineer and SOC 2 analyst. You will be given a JSON array of
subservice organization summaries (name, description, confidence). Your task is to
identify groups of names that should be canonicalized to a single canonical name.

Input JSON (truncated for readability):
{json_data}

Rules:
1. Group entries that are clearly the same organization (e.g., "AWS", "Amazon Web Services",
     "Amazon Web Services, Inc.") into a single group.
2. For each group return:
     - canonical_name: the preferred canonical name to use in output
     - variations: array of name variants that should map to canonical_name
     - reason: one-sentence justification for the merge
3. Be conservative: do not merge distinct legal entities even if names look similar.
4. Return ONLY a JSON object with a single key "groups" whose value is an array of group objects.

Example output:
{
    "groups": [
        {"canonical_name": "Amazon Web Services", "variations": ["AWS", "Amazon Web Services, Inc."], "reason": "Common brand variants and parenthetical abbreviations"}
    ]
}
"""

# Prompt used by SaaS classification to lower confidence of entries that are clearly
# SaaS/monitoring/business tools rather than subservice organizations providing core
# hosting/operational services. Expects {json_data} as input and returns a JSON object
# with an "adjustments" array of entries {"name":..., "adjust_to": <0-1>, "reason":...}
SAAS_CLASSIFICATION_PROMPT = """
You are an expert SOC 2 analyst. Given a JSON array of candidate subservice organizations
with name, description, and current confidence, identify entries that are SaaS tools
(monitoring, logging, HR, ticketing, analytics, CI/CD, etc.) which should have their
confidence reduced because they are not core subservice organizations.

Input:
{json_data}

Rules:
1. For each input item, decide whether it represents a true subservice org (hosting,
     infrastructure, managed service) or a supporting SaaS/tool.
2. If an item should be downgraded, include an adjustment object with:
     - name: exact input name
     - adjust_to: new confidence value (float between 0 and 1)
     - reason: brief justification
3. Return ONLY a JSON object with an "adjustments" array.

Example output:
{
    "adjustments": [
        {"name": "Splunk", "adjust_to": 0.3, "reason": "Logging/analytics SaaS; not core hosting provider"}
    ]
}
"""

CUEC_KEYWORDS = [
    "complementary user entity",
    "user entity control",
    "customer responsibility",
    "user responsibility",
    "user entity responsibilities",
    "customer control",
    "user control",
    "user entity is",
    "user entities are"
    # 'customer' and 'user' removed as requested
]

# SOC 1 CUEC Keywords - Focus on user entity financial reporting controls
CUEC_KEYWORDS_SOC1 = [
    "user entity control",
    "complementary user entity",
    "user organization control",
    "user entity responsibilities",
    "user entity is responsible",
    "customer is responsible",
    "user must ensure",
    "user should",
    "user entity should",
    "require user entity",
    "users are responsible",
    "financial statement preparation",
    "user entity financial",
    "user reconciliation",
    "user approval",
    "user authorization"
]

CUEC_CONSOLIDATION_PROMPT = """
You are a SOC 2 auditor consolidating extracted CUECs into a single, clean list.

## Objective
Merge duplicate or significant overlapping Complementary User Entity Controls (CUECs) while retaining the most complete version of each unique responsibility.

## Rules
1. Merge CUECs with similar descriptions, identical TSC IDs, or overlapping meaning.
2. Preserve the richest and clearest description when duplicates exist.
3. Carry forward or average confidence values.
4. Provide reasoning for each merge or retention choice.
5. Do not add commentary, markdown, or wrapper text.

## Output
Return only a JSON array where each object includes:
{{
    "cuec_seq": <int>,
    "cuec_tsc_id": "<string or null>",
    "cuec_description": "<string>",
    "cuec_line_ref": <int or null>,
    "cuec_confidence": <float>,
    "cuec_gpt_opinion": "<Yes | No>",
    "cuec_distance_from_cuec_keywords": <int or null>,
    "cuec_gpt_reasoning": "<string>",
    "cuec_framework_alignment": "<string>",
    "cuec_framework_alignment_id": "<string or null>",
    "cuec_justification": "<string>"
}}

Extracted CUECs:
{cuecs}
"""

# List of AICPA Trust Services Criteria (TSC) IDs, descriptions, and domains
TSC_CRITERIA = [
    {"id": "CC1.1", "description": "The entity demonstrates a commitment to integrity and ethical values.", "domain": "Control Environment"},
    {"id": "CC2.1", "description": "The board of directors demonstrates independence from management and exercises oversight of the development and performance of internal control.", "domain": "Control Environment"},
    {"id": "CC3.1", "description": "Management establishes, with board oversight, structures, reporting lines, and appropriate authorities and responsibilities in the pursuit of objectives.", "domain": "Control Environment"},
    {"id": "CC4.1", "description": "The entity demonstrates a commitment to attract, develop, and retain competent individuals in alignment with objectives.", "domain": "Control Environment"},
    {"id": "CC5.1", "description": "The entity holds individuals accountable for their internal control responsibilities in the pursuit of objectives.", "domain": "Control Environment"},
    {"id": "CC6.1", "description": "The entity specifies objectives with sufficient clarity to enable the identification and assessment of risks relating to objectives.", "domain": "Risk Assessment"},
    {"id": "CC6.2", "description": "The entity identifies risks to the achievement of its objectives across the entity and analyzes risks as a basis for determining how the risks should be managed.", "domain": "Risk Assessment"},
    {"id": "CC6.3", "description": "The entity considers the potential for fraud in assessing risks to the achievement of objectives.", "domain": "Risk Assessment"},
    {"id": "CC6.4", "description": "The entity identifies and assesses changes that could significantly impact the system of internal control.", "domain": "Risk Assessment"},
    {"id": "CC7.1", "description": "The entity selects and develops control activities that contribute to the mitigation of risks to the achievement of objectives to acceptable levels.", "domain": "Control Activities"},
    {"id": "CC7.2", "description": "The entity selects and develops general control activities over technology to support the achievement of objectives.", "domain": "Control Activities"},
    {"id": "CC7.3", "description": "The entity deploys control activities through policies that establish what is expected and procedures that put policies into action.", "domain": "Control Activities"},
    {"id": "CC8.1", "description": "The entity obtains or generates and uses relevant, quality information to support the functioning of internal control.", "domain": "Information and Communication"},
    {"id": "CC8.2", "description": "The entity internally communicates information, including objectives and responsibilities for internal control, necessary to support the functioning of internal control.", "domain": "Information and Communication"},
    {"id": "CC8.3", "description": "The entity communicates with external parties regarding matters affecting the functioning of internal control.", "domain": "Information and Communication"},
    {"id": "CC9.1", "description": "The entity selects, develops, and performs ongoing and/or separate evaluations to ascertain whether the components of internal control are present and functioning.", "domain": "Monitoring Activities"},
    {"id": "CC9.2", "description": "The entity evaluates and communicates internal control deficiencies in a timely manner to those parties responsible for taking corrective action, including senior management and the board of directors, as appropriate.", "domain": "Monitoring Activities"},
    {"id": "C1.1", "description": "The entity identifies and manages the inventory of information assets.", "domain": "Common Criteria - Security"},
    {"id": "C1.2", "description": "The entity restricts logical access to information assets and protected information to authorized personnel.", "domain": "Common Criteria - Security"},
    {"id": "C1.3", "description": "The entity authorizes, designs, develops, or acquires, configures, documents, tests, approves, and implements system changes.", "domain": "Common Criteria - Security"},
    {"id": "C1.4", "description": "The entity restricts physical access to information assets and protected information to authorized personnel.", "domain": "Common Criteria - Security"},
    {"id": "C1.5", "description": "The entity implements controls to prevent, detect, and mitigate security events.", "domain": "Common Criteria - Security"},
    {"id": "C1.6", "description": "The entity implements controls to prevent, detect, and mitigate security incidents.", "domain": "Common Criteria - Security"},
    {"id": "C1.7", "description": "The entity implements controls to prevent, detect, and mitigate unauthorized disclosure of protected information.", "domain": "Common Criteria - Security"},
    {"id": "C1.8", "description": "The entity implements controls to prevent, detect, and mitigate unauthorized destruction of protected information.", "domain": "Common Criteria - Security"},
    {"id": "C1.9", "description": "The entity implements controls to prevent, detect, and mitigate unauthorized use of protected information.", "domain": "Common Criteria - Security"},
    {"id": "A1.1", "description": "The entity implements controls to protect the availability of information assets.", "domain": "Availability"},
    {"id": "A1.2", "description": "The entity implements controls to prevent, detect, and mitigate availability incidents.", "domain": "Availability"},
    {"id": "P1.1", "description": "The entity implements controls to protect the privacy of personal information.", "domain": "Privacy"},
    {"id": "P2.1", "description": "The entity provides notice to data subjects about its privacy practices.", "domain": "Privacy"},
    {"id": "P3.1", "description": "The entity provides data subjects with choices regarding the collection, use, and disclosure of personal information.", "domain": "Privacy"},
    {"id": "P3.2", "description": "The entity obtains explicit consent from data subjects for the collection, use, and disclosure of personal information.", "domain": "Privacy"},
    {"id": "P4.1", "description": "The entity collects and uses personal information for purposes identified in the entity's privacy notice.", "domain": "Privacy"},
    {"id": "P5.1", "description": "The entity provides data subjects with access to their personal information for review and correction.", "domain": "Privacy"},
    {"id": "P6.1", "description": "The entity discloses personal information to third parties only for purposes identified in the entity's privacy notice.", "domain": "Privacy"},
    {"id": "P7.1", "description": "The entity implements controls to protect the quality and integrity of personal information.", "domain": "Privacy"},
    {"id": "P8.1", "description": "The entity implements controls to protect the retention and disposal of personal information.", "domain": "Privacy"},
    {"id": "P9.1", "description": "The entity implements controls to protect the transfer of personal information.", "domain": "Privacy"},
    {"id": "P10.1", "description": "The entity implements controls to protect the monitoring and enforcement of privacy practices.", "domain": "Privacy"},
    {"id": "Conf1.1", "description": "The entity identifies and maintains confidential information to meet the entity's objectives.", "domain": "Confidentiality"},
    {"id": "Conf1.2", "description": "The entity disposes of confidential information to meet the entity's objectives.", "domain": "Confidentiality"},
    {"id": "Conf1.3", "description": "The entity protects confidential information from unauthorized disclosure.", "domain": "Confidentiality"},
    {"id": "Conf1.4", "description": "The entity protects confidential information from unauthorized use.", "domain": "Confidentiality"},
    {"id": "PI1.1", "description": "The entity defines processing specifications to meet the entity's objectives.", "domain": "Processing Integrity"},
    {"id": "PI1.2", "description": "The entity implements controls to achieve processing objectives and detect and correct processing errors.", "domain": "Processing Integrity"},
    {"id": "PI1.3", "description": "The entity implements controls to protect processing from unauthorized modification.", "domain": "Processing Integrity"},
    {"id": "PI1.4", "description": "The entity implements controls to ensure system output is complete, accurate, and timely.", "domain": "Processing Integrity"},
    {"id": "PI1.5", "description": "The entity implements controls to protect the integrity of system processing.", "domain": "Processing Integrity"},
    # End of full TSC criteria list
]

# COSO Internal Control Framework (2013) Principles
COSO_2013_CRITERIA = [
    # Control Environment
    {
        'id': '1',
        'component': 'Control Environment',
        'principle': 'Demonstrates Commitment to Integrity and Ethical Values',
        'description': 'The organization demonstrates a commitment to integrity and ethical values.'
    },
    {
        'id': '2',
        'component': 'Control Environment',
        'principle': 'Exercises Oversight Responsibility',
        'description': 'The board of directors demonstrates independence from management and exercises oversight of the development and performance of internal control.'
    },
    {
        'id': '3',
        'component': 'Control Environment',
        'principle': 'Establishes Structure, Authority, and Responsibility',
        'description': 'Management establishes, with board oversight, structures, reporting lines, and appropriate authorities and responsibilities in the pursuit of objectives.'
    },
    {
        'id': '4',
        'component': 'Control Environment',
        'principle': 'Demonstrates Commitment to Competence',
        'description': 'The organization demonstrates a commitment to attract, develop, and retain competent individuals in alignment with objectives.'
    },
    {
        'id': '5',
        'component': 'Control Environment',
        'principle': 'Enforces Accountability',
        'description': 'The organization holds individuals accountable for their internal control responsibilities in the pursuit of objectives.'
    },
    # Risk Assessment
    {
        'id': '6',
        'component': 'Risk Assessment',
        'principle': 'Specifies Suitable Objectives',
        'description': 'The organization specifies objectives with sufficient clarity to enable the identification and assessment of risks relating to objectives.'
    },
    {
        'id': '7',
        'component': 'Risk Assessment',
        'principle': 'Identifies and Analyzes Risk',
        'description': 'The organization identifies risks to the achievement of its objectives across the entity and analyzes risks as a basis for determining how the risks should be managed.'
    },
    {
        'id': '8',
        'component': 'Risk Assessment',
        'principle': 'Assesses Fraud Risk',
        'description': 'The organization considers the potential for fraud in assessing risks to the achievement of objectives.'
    },
    {
        'id': '9',
        'component': 'Risk Assessment',
        'principle': 'Identifies and Analyzes Significant Change',
        'description': 'The organization identifies and assesses changes that could significantly impact the system of internal control.'
    },
    # Control Activities
    {
        'id': '10',
        'component': 'Control Activities',
        'principle': 'Selects and Develops Control Activities',
        'description': 'The organization selects and develops control activities that contribute to the mitigation of risks to the achievement of objectives to acceptable levels.'
    },
    {
        'id': '11',
        'component': 'Control Activities',
        'principle': 'Selects and Develops General Controls over Technology',
        'description': 'The organization selects and develops general control activities over technology to support the achievement of objectives.'
    },
    {
        'id': '12',
        'component': 'Control Activities',
        'principle': 'Deploys through Policies and Procedures',
        'description': 'The organization deploys control activities through policies that establish what is expected and procedures that put policies into action.'
    },
    # Information and Communication
    {
        'id': '13',
        'component': 'Information and Communication',
        'principle': 'Uses Relevant Information',
        'description': 'The organization obtains or generates and uses relevant, quality information to support the functioning of internal control.'
    },
    {
        'id': '14',
        'component': 'Information and Communication',
        'principle': 'Communicates Internally',
        'description': 'The organization internally communicates information, including objectives and responsibilities for internal control, necessary to support the functioning of internal control.'
    },
    {
        'id': '15',
        'component': 'Information and Communication',
        'principle': 'Communicates Externally',
        'description': 'The organization communicates with external parties regarding matters affecting the functioning of internal control.'
    },
    # Monitoring Activities
    {
        'id': '16',
        'component': 'Monitoring Activities',
        'principle': 'Conducts Ongoing and/or Separate Evaluations',
        'description': 'The organization selects, develops, and performs ongoing and/or separate evaluations to ascertain whether the components of internal control are present and functioning.'
    },
    {
        'id': '17',
        'component': 'Monitoring Activities',
        'principle': 'Evaluates and Communicates Deficiencies',
        'description': 'The organization evaluates and communicates internal control deficiencies in a timely manner to those parties responsible for taking corrective action, including senior management and the board of directors, as appropriate.'
    },
]

# --- SOC 1 Financial Assertions (ICFR Framework) ---
# Management assertions about financial statement controls per PCAOB AS 2201 and COSO
FINANCIAL_ASSERTIONS = [
    # Transaction-Level Assertions
    {"id": "EO", "name": "Existence/Occurrence", "category": "Transaction", 
     "description": "Transactions and events that have been recorded have occurred and pertain to the entity."},
    {"id": "C", "name": "Completeness", "category": "Transaction",
     "description": "All transactions and events that should have been recorded have been recorded."},
    {"id": "A", "name": "Accuracy", "category": "Transaction",
     "description": "Amounts and other data relating to recorded transactions and events have been recorded appropriately."},
    {"id": "CO", "name": "Cutoff", "category": "Transaction",
     "description": "Transactions and events have been recorded in the correct accounting period."},
    {"id": "CL", "name": "Classification", "category": "Transaction",
     "description": "Transactions and events have been recorded in the proper accounts."},
    
    # Account Balance Assertions
    {"id": "E", "name": "Existence", "category": "Account Balance",
     "description": "Assets, liabilities, and equity interests exist."},
    {"id": "R", "name": "Rights and Obligations", "category": "Account Balance",
     "description": "The entity holds or controls the rights to assets, and liabilities are the obligations of the entity."},
    {"id": "CV", "name": "Completeness and Valuation", "category": "Account Balance",
     "description": "All account balances that should be recorded have been recorded at appropriate amounts."},
    
    # Presentation and Disclosure Assertions
    {"id": "OC", "name": "Occurrence and Rights", "category": "Presentation",
     "description": "Disclosed events, transactions, and other matters have occurred and pertain to the entity."},
    {"id": "CD", "name": "Completeness (Disclosure)", "category": "Presentation",
     "description": "All disclosures that should have been included in the financial statements have been included."},
    {"id": "CU", "name": "Classification and Understandability", "category": "Presentation",
     "description": "Financial information is appropriately presented and described, and disclosures are clearly expressed."},
    {"id": "AV", "name": "Accuracy and Valuation", "category": "Presentation",
     "description": "Financial and other information are disclosed fairly and at appropriate amounts."},
    
    # Common Financial Reporting Control Objectives
    {"id": "REV", "name": "Revenue Recognition", "category": "Control Objective",
     "description": "Controls over revenue recognition, including timing and measurement."},
    {"id": "AP", "name": "Accounts Payable", "category": "Control Objective",
     "description": "Controls over vendor invoices, payment processing, and accounts payable balances."},
    {"id": "AR", "name": "Accounts Receivable", "category": "Control Objective",
     "description": "Controls over customer invoicing, collections, and accounts receivable balances."},
    {"id": "INV", "name": "Inventory", "category": "Control Objective",
     "description": "Controls over inventory counts, valuation, and cost of goods sold."},
    {"id": "PPE", "name": "Property, Plant & Equipment", "category": "Control Objective",
     "description": "Controls over fixed asset acquisitions, depreciation, and disposals."},
    {"id": "PAY", "name": "Payroll", "category": "Control Objective",
     "description": "Controls over payroll processing, employee data, and compensation."},
    {"id": "CASH", "name": "Cash Management", "category": "Control Objective",
     "description": "Controls over cash receipts, disbursements, and bank reconciliations."},
    {"id": "JE", "name": "Journal Entries", "category": "Control Objective",
     "description": "Controls over manual and automated journal entries."},
    {"id": "FR", "name": "Financial Reporting", "category": "Control Objective",
     "description": "Controls over period-end close, consolidation, and financial statement preparation."},
    {"id": "TAX", "name": "Tax Compliance", "category": "Control Objective",
     "description": "Controls over tax calculations, filings, and compliance."},
]

# Keywords for auto-mapping controls to financial assertions
FINANCIAL_ASSERTION_KEYWORDS = {
    "EO": ["occurrence", "occurred", "validity", "valid transaction", "authorization", "approve"],
    "C": ["completeness", "complete", "all transactions", "missing", "omission"],
    "A": ["accuracy", "accurate", "calculation", "compute", "mathematical", "precision"],
    "CO": ["cutoff", "period end", "period-end", "accrual", "timing", "correct period"],
    "CL": ["classification", "classify", "proper account", "account coding", "chart of accounts"],
    "E": ["existence", "physical", "confirm", "verification", "inventory count", "asset verification"],
    "R": ["rights", "obligations", "ownership", "legal", "contract", "agreement"],
    "CV": ["valuation", "fair value", "impairment", "carrying amount", "measurement"],
    "OC": ["disclosure", "note", "footnote", "presentation"],
    "CD": ["disclosure completeness", "all disclosures", "required disclosure"],
    "CU": ["understandability", "clarity", "presentation", "format"],
    "AV": ["disclosure accuracy", "fair presentation"],
    "REV": ["revenue", "sales", "income", "billing", "invoice customer"],
    "AP": ["accounts payable", "vendor", "supplier", "purchase", "payable"],
    "AR": ["accounts receivable", "customer", "collections", "receivable", "credit"],
    "INV": ["inventory", "stock", "goods", "cost of sales", "COGS"],
    "PPE": ["fixed asset", "property", "equipment", "depreciation", "capital"],
    "PAY": ["payroll", "compensation", "salary", "wage", "employee"],
    "CASH": ["cash", "bank", "reconciliation", "payment", "receipt"],
    "JE": ["journal entry", "manual entry", "adjustment", "posting"],
    "FR": ["financial reporting", "close", "consolidation", "financial statement"],
    "TAX": ["tax", "income tax", "sales tax", "VAT", "withholding"],
}

# Confidence threshold for financial assertion mappings
FINANCIAL_ASSERTION_CONFIDENCE_THRESHOLD = 0.60  # 60% minimum confidence to include
FINANCIAL_ASSERTION_MAX_REASONING_CHARS = 200  # Character limit for reasoning text

# --- Control Section Mappings for Extractors ---
# TSC Section mapping (provided)
control_tsc_sections = {
    "Control Environment (CC1.1 - CC1.5)": ["CC1.1", "CC1.2", "CC1.3", "CC1.4", "CC1.5"],
    "Risk Assessment (CC2.1 - CC2.4)": ["CC2.1", "CC2.2", "CC2.3", "CC2.4"],
    "Control Activities (CC3.1 - CC3.4)": ["CC3.1", "CC3.2", "CC3.3", "CC3.4"],
    "Information & Communication (CC4.1 - CC4.2)": ["CC4.1", "CC4.2"],
    "Monitoring Activities (CC5.1 - CC5.5)": ["CC5.1", "CC5.2", "CC5.3", "CC5.4", "CC5.5"],
    "Logical & Physical Access Controls (CC6.1 - CC6.10)": ["CC6.1", "CC6.2", "CC6.3", "CC6.4", "CC6.5", "CC6.6", "CC6.7", "CC6.8", "CC6.9", "CC6.10"],
    "System Operations (CC7.1 - CC7.5)": ["CC7.1", "CC7.2", "CC7.3", "CC7.4", "CC7.5"],
    "Change Management (CC8.1)": ["CC8.1"],
    "Risk Mitigation (CC9.1 - CC9.2)": ["CC9.1", "CC9.2"],
    "Availability (A1.1 - A1.3)": ["A1.1", "A1.2", "A1.3"],
    "Processing Integrity (PI1.1 - PI1.4)": ["PI1.1", "PI1.2", "PI1.3", "PI1.4"],
    "Confidentiality (C1.1 - C1.4)": ["C1.1", "C1.2", "C1.3", "C1.4"],
    "Privacy (P1.1 - P6.1)": ["P1.1", "P2.1", "P3.1", "P4.1", "P5.1", "P6.1"]
}

# COSO Section mapping (by component/principle)
control_coso_sections = {
    "Control Environment (1-5)": ["1", "2", "3", "4", "5"],
    "Risk Assessment (6-9)": ["6", "7", "8", "9"],
    "Control Activities (10-12)": ["10", "11", "12"],
    "Information & Communication (13-15)": ["13", "14", "15"],
    "Monitoring Activities (16-17)": ["16", "17"]
}

# Optional: SOC Domain mapping (TSC/COSO)
control_soc_domains = {
    "Security": ["CC", "C"],
    "Availability": ["A"],
    "Processing Integrity": ["PI"],
    "Confidentiality": ["Conf"],
    "Privacy": ["P"]
}

# Prompt for extracting tested controls from the Control_Descriptions section
CONTROL_EXTRACTION_PROMPT = """
You are an expert SOC 2 control analyst. Your task is to extract a single control (and its related fields) from the provided text.

## Objective
Analyze the text chunk (beginning at line {start_line}) and return one control record in structured JSON format.  
Focus only on explicit, self-contained control information — not inferred or overlapping content.

## Extraction Rules
1. **Control ID**
    - Look for one or more identifiers (combinations of letters that are usually all capitalized, numbers, strings separated by dashes, etc. like “CC6.1” or "EL-06-02").
    - If multiple IDs appear, select the most detailed set associated with this control.  For example, if both “CC6.1” and “CC6.1a” appear, choose “CC6.1a”.  Or if “CC6.1” and “EL-06-02” both appear, include both.  In some cases, you may see a primary ID plus sub-IDs (e.g., “CC6.1” and “CC6.1a”); include all relevant IDs. You may also see a TSC ID plus an internal company code; include both.
2. **Control Description**
    - Extract 1–5 sentences or a concise bullet list describing the control’s intent and implementation.
    - Keep the text as close to the original phrasing as possible.  Try to differentiate between control description, test procedures, results, control requirements, and entity controls.
3. **Additional References**
    - Capture any secondary identifiers or cross-references linked to this control.
4. **Testing Comments**
    - Identify language describing testing performed by the auditor (“examined”, “inquired”, “inspected”, “tested”, “observed”, etc.).
5. **Test Results**
    - Extract text summarizing the auditor’s test results.
    - Do not include content that clearly belongs to a following control or section.
6. **Deviation Assessment**
    - Based only on the test results text, determine if a deviation/exception/problem is explicitly stated.
    - If present, set has_deviation = true and provide a short, factual deviation_desc.
    - Otherwise, set has_deviation = false and leave deviation_desc empty.
7. **Ending Line Number**
    - Estimate the line where this control’s text logically ends.
8. **Confidence**
    - Provide a float (0–1) indicating confidence in the completeness and accuracy of the extraction.
    - Add a brief justification.

## Output Format
Return only one JSON object with this structure:
{{
  "control_id": "<string>",
  "control_desc": "<string>",
  "control_test": "<string>",
  "control_test_results": "<string>",
  "has_deviation": <true or false>,
  "deviation_desc": "<string>",
  "additional_references": ["<string>", ...],
  "end_line": <integer>,
  "control_confidence": <float>,
  "control_gpt_conf_justification": "<string>"
}}

Text to analyze (starting at line {start_line}):
{text}
"""

# Prompt for consolidating and deduplicating extracted controls
CONTROL_CONSOLIDATION_PROMPT = """
You are an expert SOC 2 control auditor. Your task is to merge and deduplicate extracted controls.

## Objective
Combine controls that were likely split during chunking operations.

## Rules
1. Merge controls sharing the same control_id or nearly identical descriptions.
2. Preserve the most complete and representative description.
3. Combine or average relevant confidence values.
4. Add reasoning for every merge or retention decision.
5. Maintain a clean, flat list of unique controls — no wrapper objects, no commentary.

## Output
Return only a JSON array of consolidated controls, where each object contains:
{{
    "control_seq": <int>,
    "control_id": "<string>",
    "control_desc": "<string>",
    "control_test": "<string>",
    "control_test_results": "<string>",
    "control_page_ref": "<string or null>",
    "control_line_ref": <int or null>,
    "control_gpt_opinion": "<string or null>",
    "control_gpt_reasoning": "<string>",
    "control_confidence": <float or null>
}}

Extracted Controls:
{controls}
"""

# Optimized GPT-5: Section analysis breakpoint detection
CHUNK_ANALYSIS_PROMPT = """
You are a SOC 2 control section analyst. Your task is to identify logical breakpoints in the provided text where individual control sections start or end.

## Objective
Examine the given text and return a list of character offsets that mark likely boundaries between separate controls or sections.

## Rules
1. Use only the provided text — do not infer or assume missing context.
2. Look for structural clues that signal a new control:
    - Control IDs (e.g., “CC6.1”, “A1.2”, or numbered codes)
    - Headings, bold identifiers, or bullet/numbered lists starting midline
    - Transitional audit language (“The auditor tested…”, “No deviations were noted…”, etc.)
3. Avoid splitting inside paragraphs that clearly belong to the same control.
4. Do not infer missing headers or insert artificial breakpoints.
5. If no clear breakpoints exist, return an empty list.

## Output
Return only a JSON array of integers representing character offsets.

SOC 2 Report Text:
{text}
"""

# Optimized GPT-5: Segment classification for SOC 2 controls
SEGMENT_CLASSIFICATION_PROMPT = """
You are an expert SOC 2 document classifier. Categorize each segment of the provided text into its appropriate role.

## Objective
Identify which part of the SOC 2 control lifecycle each segment belongs to.

## Valid Categories
- control_id
- control_description
- test_procedure
- test_result

## Rules
1. Classify based only on the text content — do not assume beyond what is shown.
2. Each segment should map to exactly one of the four valid categories.
3. Use contextual cues:
     - IDs or alphanumeric codes → control_id
     - Descriptive, policy-style sentences → control_description
     - Auditor actions (examined, inspected, inquired) → test_procedure
     - Outcome/result language (no deviations, exceptions found, etc.) → test_result
4. If the text does not fit any category, omit it from output.

## Output
Return a JSON array of objects:
[
    {{"type": "control_id", "text": "<...>"}},
    {{"type": "control_description", "text": "<...>"}},
    ...
]

SOC 2 Report Text:
{text}
"""

# Optimized GPT-5: Dynamic chunk header detection
DYNAMIC_CHUNKING_PROMPT = """
You are segmenting a SOC 2 report into logical control chunks.

## Objective
Identify the exact numeric character position (0-based index) in the text where each control section header starts.

## Rules
1. Base your detection solely on actual heading patterns or identifiers (e.g., “CC6.1”, “A1.2”, “Control ID”).
2. Do not infer missing headers or create artificial positions.
3. Return precise numeric offsets only — not summaries or prose.
4. If no control headers are found, return an empty array.

## Output
Return only a JSON array of integers (character positions).

SOC 2 Report Text:
{text}
"""

# Optimized GPT-5: Section heading validation as a dedicated constant
SECTION_HEADING_VALIDATION_PROMPT = """
You are verifying whether the marked line represents a valid section heading in a SOC 2 report.

## Rules
1. Headings typically appear in title case, may include roman numerals or numbering, and stand alone on their line.
2. Lines forming part of a paragraph or containing punctuation beyond numbering are not headings.
3. Consider surrounding text to judge if the line visually or semantically separates sections.
4. Output only “Yes” or “No” followed by a short justification.

## Output
Yes – <reason>  
No – <reason>

Context:
{text}
>>> {line}
"""

# Optimized GPT-5: Refined chunk analysis offsets
CHUNK_ANALYSIS_PROMPT_REFINED = """
You are analyzing a SOC 2 report section to detect potential control boundaries.

## Objective
List the precise character offsets where each control or subsection likely begins.

## Guidance
- Recognize section transitions through control identifiers, bullet patterns, or repeated audit phrases.
- Avoid splitting text within continuous paragraphs or mid-sentences.
- Return only a JSON array of integer offsets (no explanations or markup).

SOC 2 Report Text:
{text}
"""

## Note: Legacy minimal overrides removed; using optimized versions defined above.

# Minimal prompt to evaluate deviation strictly from control_test_results
DEVIATION_EVAL_PROMPT = """
You are a SOC 2 auditor. Determine if the provided control_test_results text contains an explicit deviation, exception, or finding.

## Rules
1. Base your decision ONLY on the provided control_test_results — do not infer.
2. Mark has_deviation = false if the text states “no deviations noted” or any similar clean result.
3. Mark has_deviation = true only if the text clearly reports a deviation, exception, or issue.
4. When has_deviation = true, summarize the issue in one short sentence (deviation_desc).
5. If uncertain, default to has_deviation = false.

## Output
Return only a valid JSON object:
{{
    "has_deviation": <true or false>,
    "deviation_desc": "<string if true, else empty>"
}}

Context:
Control ID: {control_id}
Control Description: {control_desc}
Control Test: {control_test}
Control Test Results:
<<<
{control_test_results}
>>>
"""

# --- Control Extraction Testing Config ---
CONTROL_TESTING_ENABLED = False  # Set to False to disable test mode and process the full file
CONTROL_TESTING_MAX_LINE = 2000  # Only process up to this line number when testing is enabled

# Hang prevention safeguards for control extraction
CONTROL_HANG_PREVENTION_ENABLED = True  # Enable hang prevention safeguards
CONTROL_MAX_PROCESSING_MINUTES = 60     # Maximum processing time before timeout
CONTROL_MAX_CONSECUTIVE_FAILURES = 10   # Stop after this many consecutive failures
CONTROL_DETECT_NON_CONTROL_CONTENT = False  # Detect and stop at mapping tables/non-control content (disabled due to false positives)

# --- Control Stall Watchdog ---
# If no forward line progress for CONTROL_STALL_MAX_IDLE_SECONDS, forcibly advance by CONTROL_STALL_FORCE_ADVANCE_LINES
# Set CONTROL_STALL_MAX_IDLE_SECONDS=0 to disable.
CONTROL_STALL_MAX_IDLE_SECONDS = int(os.getenv('CONTROL_STALL_MAX_IDLE_SECONDS', '180'))
CONTROL_STALL_FORCE_ADVANCE_LINES = int(os.getenv('CONTROL_STALL_FORCE_ADVANCE_LINES', '120'))

# List of key test words to check in control_desc for confidence adjustment
CONTROL_TEST_WORDS = [
    "examined",
    "inquired",
    "ascertained",
    "inspected",
    "evaluated"
]

# --- Control Extractor v2 Chunking/Overlap Settings ---
# Lines per chunk and overlap/tail-guard lines to reduce control splits across chunks
CONTROL_LINES_PER_CHUNK = 160
CONTROL_CHUNK_OVERLAP_LINES = 40
CONTROL_CHUNK_TAIL_GUARD_LINES = 8

# =============================================================================
# CONTROL EXTRACTOR V4 - AWARE-CHUNK + CHAIN-OF-THOUGHT CONFIGURATION
# =============================================================================

# Control Extractor Version Selection
# Options: "v2" (legacy line-based) or "v4" (aware-chunk + CoT)
CONTROL_EXTRACTOR_VERSION = os.getenv("CONTROL_EXTRACTOR_VERSION", "v4")

# V4 Architecture: Token-based aware chunking with continuation handling
CONTROL_V4_TOKENS_PER_CHUNK = 500       # Approximate tokens per chunk (~4 chars = 1 token) - balanced for various report formats
CONTROL_V4_OVERLAP_TOKENS = 100         # Token overlap between chunks for context continuity
CONTROL_V4_MIN_CONFIDENCE = 0.5         # Minimum confidence threshold (controls below are filtered)
CONTROL_V4_SAVE_REJECTED = True         # Save rejected low-confidence controls for review

# V4 Prompt: Multi-control extraction with linguistic cue detection and CoT reasoning
CONTROL_EXTRACTION_PROMPT_V4 = """
You are a SOC 2 / COSO control extraction model. From unstructured SOC 2 text with all table structure removed, extract ALL complete control blocks in this chunk.

## Goal
Extract ALL complete control blocks found in this chunk. For each control, return:
- the control identifier (if present)
- the control description
- one or more auditor test procedures
- one or more test results
- whether a deviation/exception is stated
- where this control logically ends (line number estimate)

## Expected Output
Return a JSON object with a "controls" array containing one object per control found:

{{
  "controls": [
    {{
      "control_id": "<string or null>",
      "control_desc": "<string>",
      "control_tests": ["<string>", "<string>", ...],
      "control_test_results": ["<string>", "<string>", ...],
      "has_deviation": <true or false>,
      "deviation_desc": "<string>",
      "additional_references": [],
      "end_line": <integer>,
      "control_confidence": <float>,
      "control_gpt_conf_justification": "<short reasoning>",
      "continuation": <true or false>
    }},
    ... (repeat for each control found)
  ]
}}

If only one control is found, return an array with one element.
If a control starts but doesn't complete in this chunk, set "continuation": true for that control.

## Parsing Strategy
Analyze linguistic and structural cues — never rely on visible table columns.

### 1. Ignore structural noise
Skip any line that appears to be a **domain header** (e.g., "Communication and Information", "Logical and Physical Access")
or a **principle statement** (e.g., "CC2.1 COSO Principle 13: …", "Common Criteria Related to…").  
These provide section context only.

### 2. Detect control boundaries
Use these indicators to start a new control block:
- Control identifiers like "CC2.1.1", "CC5.2.2", "ELC-01-02", "1 ", "2."
- Entity-voice text starting with "The company…", "The entity…", "Personnel…"
- Auditor verbs in past tense ("Inspected…", "Observed…", "Tested…", "Inquired…") after a previous result line.
Stop the block when a new control ID, header, or whitespace separator appears.

### 3. Classify sentences by role
- **control_desc** – present-tense statements about control operation.
- **control_tests[]** – auditor-voice procedures (verbs like "inspected", "tested", "inquired").
- **control_test_results[]** – concise evaluations like "No exceptions noted."  
  Record all, deduplicating identical phrases.

### 4. Deviation detection
- has_deviation = true if any result mentions "exception", "deviation", "failure", or "not effective".
- deviation_desc = the phrase or short summary.
- Otherwise, has_deviation = false and deviation_desc = "".

### 5. Boundary sanity
If a domain or principle header appears mid-text, treat it as the start of a new section and stop accumulating text.

### 6. Confidence scoring
- 0.9–1.0 → found control_id + description + ≥1 test + result.
- 0.6–0.89 → missing ID but strong control/test/result linkage.
- 0.3–0.59 → partial or inferred control.
Include a brief justification.

### 7. Continuation flag
If this chunk ends mid-control (incomplete description or missing results), set "continuation": true for that control.
Otherwise, set "continuation": false.

### 8. Multiple controls in chunk
Extract ALL complete controls found in this chunk. The chunk may contain:
- Zero controls (just headers or narrative)
- One control (typical for sparse reports)
- Multiple controls (typical for dense reports like Adobe, KPMG)
- Partial control (starts but doesn't complete - mark as continuation)

Analyze this text (first line is line {start_line}). Extract ALL control blocks found:
{text}
"""

# V4 SOC 1 Prompt: Control extraction with financial assertion mapping
CONTROL_EXTRACTION_PROMPT_V4_SOC1 = """
You are a SOC 1 Type 2 control extraction model specialized in Internal Control over Financial Reporting (ICFR). From unstructured SOC 1 text with all table structure removed, extract ALL complete control blocks in this chunk.

## Goal
Extract ALL complete control blocks found in this chunk. For each control, return:
- the control identifier (if present)
- the control description (financial reporting focus)
- one or more auditor test procedures
- one or more test results
- whether a deviation/exception is stated
- which financial assertions this control addresses
- where this control logically ends (line number estimate)

## Expected Output
Return a JSON object with a "controls" array containing one object per control found:

{{
  "controls": [
    {{
      "control_id": "<string or null>",
      "control_desc": "<string>",
      "control_tests": ["<string>", "<string>", ...],
      "control_test_results": ["<string>", "<string>", ...],
      "has_deviation": <true or false>,
      "deviation_desc": "<string>",
      "financial_assertions": ["EO", "C", "A", "CV", ...],
      "assertion_reasoning": "<brief explanation of assertion mapping>",
      "end_line": <integer>,
      "control_confidence": <float>,
      "control_gpt_conf_justification": "<short reasoning>",
      "continuation": <true or false>
    }},
    ... (repeat for each control found)
  ]
}}

## Financial Assertions (Management Assertions per PCAOB AS 2201)
Map each control to relevant assertions:
- **EO** (Existence/Occurrence): Transactions occurred and pertain to entity
- **C** (Completeness): All transactions recorded
- **A** (Accuracy): Amounts recorded appropriately
- **CO** (Cutoff): Transactions in correct period
- **CL** (Classification): Transactions in proper accounts
- **E** (Existence - Balance): Assets, liabilities exist
- **R** (Rights and Obligations): Entity holds/controls rights
- **CV** (Completeness and Valuation): Balances at appropriate amounts
- **REV** (Revenue Recognition): Revenue controls
- **AP** (Accounts Payable): Vendor payment controls
- **AR** (Accounts Receivable): Customer billing controls
- **INV** (Inventory): Inventory controls
- **PPE** (Property, Plant & Equipment): Fixed asset controls
- **PAY** (Payroll): Compensation controls
- **CASH** (Cash Management): Cash controls
- **JE** (Journal Entries): Journal entry controls
- **FR** (Financial Reporting): Period-end close controls
- **TAX** (Tax Compliance): Tax controls

## Parsing Strategy
Analyze linguistic and structural cues — never rely on visible table columns.

### 1. Ignore structural noise
Skip lines that are domain headers (e.g., "Financial Reporting Controls", "Transaction Processing")
or section titles. These provide context only.

### 2. Detect control boundaries
Use these indicators to start a new control block:
- Control identifiers like "FR-001", "REV-01", "AP.02", "1 ", "2."
- Entity-voice text starting with "The company…", "Management…", "Finance personnel…"
- Auditor verbs in past tense ("Inspected…", "Observed…", "Tested…", "Inquired…") after a previous result line.
Stop the block when a new control ID, header, or whitespace separator appears.

### 3. Classify sentences by role
- **control_desc** – present-tense statements about control operation with financial reporting context
- **control_tests[]** – auditor-voice procedures (verbs like "inspected", "tested", "inquired")
- **control_test_results[]** – concise evaluations like "No exceptions noted"

### 4. Deviation detection
- has_deviation = true if any result mentions "exception", "deviation", "failure", or "not effective"
- deviation_desc = the phrase or short summary
- Otherwise, has_deviation = false and deviation_desc = ""

### 5. Financial assertion mapping
Analyze control_desc and identify which financial assertions are addressed:
- Look for transaction cycle keywords (revenue, purchases, payroll, inventory)
- Look for assertion keywords (completeness, accuracy, existence, authorization, cutoff)
- Look for account balance references (AR, AP, cash, PPE, revenue, COGS)
- List ALL applicable assertion codes in financial_assertions array
- Provide brief reasoning in assertion_reasoning (max 150 chars)

### 6. Confidence scoring
- 0.9–1.0 → found control_id + description + ≥1 test + result + clear assertion mapping
- 0.6–0.89 → missing ID but strong control/test/result linkage with assertions
- 0.3–0.59 → partial or inferred control
Include a brief justification.

### 7. Continuation flag
If this chunk ends mid-control (incomplete description or missing results), set "continuation": true for that control.
Otherwise, set "continuation": false.

### 8. Multiple controls in chunk
Extract ALL complete controls found in this chunk. The chunk may contain:
- Zero controls (just headers or narrative)
- One control (typical for sparse reports)
- Multiple controls (typical for dense reports)
- Partial control (starts but doesn't complete - mark as continuation)

Analyze this text (first line is line {start_line}). Extract ALL control blocks found:
{text}
"""

# --- Deviation Detection Heuristics (English-only) ---
# Positive signals indicate an exception/deviation; negatives indicate clean results
# These are regex patterns (case-insensitive). Customize as needed.
## Removed: deviation regex patterns (heuristics no longer used)

TABLE_FIELD_MAP = {
    "company": ["name", "parent_company", "confidence", "scan_id"],
    "control": [
        "control_id", "control_desc", "control_test", "control_test_results", "has_deviation", "deviation_desc", "control_page_refs", "control_line_ref", "control_seq",
        "control_tsc_id", "control_coso_id", "control_tsc_similarity", "control_coso_similarity", "control_tsc_confidence_pct",
        "control_coso_confidence_pct", "control_closest_framework", "control_tsc_section", "control_coso_section", "control_soc_domain",
        "control_status", "merged_to_control_id", "control_gpt_opinion", "control_gpt_reasoning", "control_confidence", "confidence_calc", "scan_id"
    ],
    "cuec": [
        "cuec_seq", "cuec_tsc_id", "cuec_description", "cuec_line_ref", "cuec_confidence", "cuec_gpt_opinion",
        "cuec_distance_from_cuec_keywords", "cuec_gpt_reasoning", "cuec_framework_alignment", "cuec_framework_alignment_id",
        "cuec_justification", "cuec_coso_id", "cuec_tsc_similarity", "cuec_coso_similarity", "cuec_tsc_confidence_pct",
        "cuec_coso_confidence_pct", "cuec_closest_framework", "cuec_confidence_justification", "annotation", "control_strength", "scan_id"
    ],
    "subservice_org": ["name", "confidence", "scan_id"],
    "product": ["name", "scan_id"]
}

## Note: Removed legacy minimal SUBSERVICE_ORG_GPT_VERIFY_PROMPT override; retaining optimized JSON version defined earlier.

SUBSERVICE_ORGS_TXT_PATH = str(PROJECT_ROOT / 'backend' / 'app' / 'extractors' / 'subservice_orgs.txt')

# === Multi-Match Framework Mapping Prompts (Adaptive Token Management) ===

FRAMEWORK_CATEGORY_SELECTION_PROMPT = """
You are an expert SOC 2 auditor analyzing controls for AICPA TSC framework alignment.

Control Description:
{control_desc}

Score each TSC category from 0-10 based on relevance to this control:
- Common Criteria (CC1-CC9): General governance, risk assessment, control activities, communication, monitoring
- Security (C1.x): Logical/physical access, change management, security event/incident response
- Availability (A1.x): System availability, recovery procedures
- Privacy (P*.x): Personal information collection, use, disclosure, retention
- Confidentiality (Conf*.x): Confidential information protection
- Processing Integrity (PI*.x): Processing accuracy, completeness, timeliness

Respond ONLY with JSON:
{{
  "category_scores": [
    {{"category": "Common Criteria", "score": 0-10}},
    {{"category": "Security (C1.x)", "score": 0-10}},
    {{"category": "Availability (A1.x)", "score": 0-10}},
    {{"category": "Privacy (P*.x)", "score": 0-10}},
    {{"category": "Confidentiality (Conf*.x)", "score": 0-10}},
    {{"category": "Processing Integrity (PI*.x)", "score": 0-10}}
  ],
  "reasoning": "Brief 1-sentence explanation of top scoring categories"
}}

Select categories with score ≥ 7. If control is general/governance, emphasize Common Criteria.
If control is technical/operational, emphasize specific domain categories.
"""

FRAMEWORK_MULTI_MATCH_PROMPT_TSC = """
You are an expert SOC 2 auditor. Select the top 3-5 most relevant AICPA TSC criteria for this control.

Control Description:
{control_desc}

{deviation_context}

Available TSC Criteria (with full descriptions):
{tsc_criteria_list}

## Semantic Matching Guidelines:

**Look for synonyms and related concepts:**
- "backup" / "restore" / "recovery" / "data replication" → Availability (A1.x)
- "access control" / "authentication" / "authorization" / "user provisioning" / "identity management" → Security (C1.2)
- "change management" / "change control" / "deployment" / "SDLC" → Security (C1.3)
- "monitoring" / "logging" / "alerting" / "SIEM" → Security (C1.5, C1.6)
- "incident response" / "security events" / "threat detection" → Security (C1.5, C1.6)
- "encryption" / "data protection" / "secure transmission" → Security (C1.7) or Confidentiality (Conf1.3)
- "risk assessment" / "risk identification" / "risk analysis" → Risk Assessment (CC6.x)
- "policies" / "procedures" / "documentation" / "standards" → Control Activities (CC7.3)
- "DR testing" / "disaster recovery drill" / "business continuity" / "failover testing" → Availability (A1.1, A1.2)
- "penetration testing" / "vulnerability scanning" / "security testing" → Security (C1.5)
- "privacy notice" / "consent" / "data subject rights" / "GDPR" → Privacy (P*.x)

## Multi-Mapping Rules:

**A single control often maps to MULTIPLE TSC criteria** when it:
1. Addresses multiple aspects (e.g., backup with access controls → A1.1 + C1.2)
2. Involves both general governance and specific technical controls (e.g., CC7.2 + C1.3)
3. Spans multiple phases (e.g., risk assessment + control implementation → CC6.2 + CC7.1)
4. Includes monitoring components (e.g., primary control + monitoring → C1.x + CC9.1)

**Examples of multi-mapping:**
- "Access control policies with annual review" → C1.2 (access control) + CC7.3 (policies) + CC9.1 (review)
- "Backup procedures with encryption" → A1.1 (backup) + C1.7 (encryption)
- "Change management with testing" → C1.3 (change management) + PI1.2 (testing/accuracy)
- "Incident response with logging" → C1.6 (incident response) + C1.5 (event detection)

## Matching Instructions:

1. **Semantic Keyword Matching**: Match control intent using synonyms and related terms (not just exact keywords)

2. **Domain Alignment**: Consider primary and secondary domains
   - Primary: Main focus of control
   - Secondary: Supporting aspects of control

3. **Deviation Consideration**: If deviation exists, ADD criteria related to:
   - Monitoring (CC9.x) - regardless of primary domain
   - Deficiency reporting (CC9.2)
   - Control evaluation (CC9.1)

4. **Return 3-5 matches** (not just top 3):
   - Include all criteria with confidence ≥ 0.6
   - Prefer more matches with distinct reasoning over fewer matches
   - Each match must address a DIFFERENT aspect of the control

5. **Reasoning Structure**: For each match, provide:
   - Semantic keywords from control (including synonyms identified)
   - Specific aspect of control this criterion addresses
   - Domain/intent alignment explanation

Respond ONLY with JSON:
{{
  "matches": [
    {{
      "id": "TSC ID (e.g., CC7.2)",
      "confidence": 0.0-1.0,
      "keywords_matched": ["keyword1", "synonym1", "related_term1"],
      "aspect_addressed": "Which specific part of control this criterion covers",
      "reasoning": "Specific explanation with semantic matches (100 chars max)"
    }}
  ]
}}

**Return 3-5 matches** (extend to 5 if multiple strong matches exist).
Include only matches with confidence ≥ 0.6.
Each match MUST have DISTINCT TSC ID and address a DIFFERENT aspect of the control.
IMPORTANT: Do not limit to 3 - return up to 5 matches if warranted.
If no good matches exist, return {{"matches": []}}.
"""

FRAMEWORK_MULTI_MATCH_PROMPT_COSO = """
You are an expert SOC 2 auditor. Select the top 3-5 most relevant COSO 2013 principles for this control.

Control Description:
{control_desc}

{deviation_context}

Available COSO 2013 Principles (with full descriptions):
{coso_criteria_list}

## COSO Semantic Mapping Guide:

**Control Environment (P1-5)**: Organizational foundation
- P1: Integrity, ethics, code of conduct, ethical culture, values, tone at the top
- P2: Board oversight, governance, board independence, board meetings, audit committee
- P3: Organizational structure, reporting lines, authority, responsibility, roles, segregation of duties
- P4: Competence, hiring, training, development, retention, succession planning, skills
- P5: Accountability, performance measures, incentives, consequences, enforcement, discipline

**Risk Assessment (P6-9)**: Risk identification and management
- P6: Objectives, strategic goals, operational objectives, compliance objectives, objective setting
- P7: Risk identification, risk analysis, risk evaluation, inherent risk, residual risk, risk appetite
- P8: Fraud risk, fraud schemes, fraud prevention, fraud detection, anti-fraud programs
- P9: Change assessment, business changes, regulatory changes, technology changes, change impact

**Control Activities (P10-12)**: Specific control implementation
- P10: Control selection, control design, preventive controls, detective controls, risk mitigation, compensating controls
- P11: Technology controls, IT general controls, access controls, change controls, operations controls, IT security
- P12: Policies, procedures, standards, guidelines, documentation, control deployment, formalization

**Information & Communication (P13-15)**: Data and reporting
- P13: Information quality, data accuracy, data relevance, data timeliness, data completeness, reporting
- P14: Internal communication, top-down communication, bottom-up communication, whistleblower, issue escalation
- P15: External communication, stakeholder reporting, regulatory reporting, customer communication, vendor communication

**Monitoring Activities (P16-17)**: Control evaluation
- P16: Control testing, control reviews, ongoing evaluations, separate evaluations, management reviews, internal audit, control assessments
- P17: Deficiency identification, deficiency reporting, deficiency communication, remediation, corrective action

## Multi-Mapping Rules:

**A single control typically maps to MULTIPLE COSO principles** because:
1. Controls span multiple components (e.g., technical control → P11 + P10)
2. Controls include monitoring/review → Always add P16 or P17
3. Controls require documentation → Add P12
4. Controls involve communication → Add P14 or P15

**Common multi-mapping patterns:**
- "Access control policy with quarterly review" → P11 (technology) + P12 (policies) + P16 (review)
- "Backup procedures documented and tested" → P11 (technology) + P12 (procedures) + P16 (testing)
- "Risk assessment process with board reporting" → P7 (risk analysis) + P15 (external communication to board)
- "Change management with approval workflow" → P11 (technology controls) + P9 (change assessment)
- "Incident response with escalation procedures" → P11 (security controls) + P14 (internal communication)

## Semantic Keyword Mapping:

- "backup/restore/recovery" → P11 (technology controls) + P10 (risk mitigation)
- "access control/authentication" → P11 (technology controls)
- "monitoring/logging/alerting" → P16 (ongoing evaluations) + P11 (technology)
- "policies/procedures/documentation" → P12 (policies and procedures)
- "training/awareness" → P4 (competence)
- "review/testing/audit" → P16 (evaluations)
- "exception/deviation/deficiency" → P17 (deficiency communication)
- "reporting/escalation/communication" → P14 (internal) or P15 (external)
- "risk assessment/risk analysis" → P7 (risk identification)
- "change management/change control" → P9 (change assessment) + P11 (technology)

## Matching Instructions:

1. **Identify ALL relevant components**: Most controls touch 2-4 COSO principles

2. **Component Mapping**:
   - Technical/IT controls → Almost always P11 (technology controls)
   - Control documentation → Almost always P12 (policies/procedures)
   - Control monitoring/testing → Almost always P16 (evaluations)
   - Deficiencies/exceptions → Almost always P17 (deficiency communication)

3. **Semantic Matching**: Use synonyms and related concepts
   - "backup" relates to P11 even if "technology" not mentioned
   - "quarterly review" relates to P16 even if "monitoring" not mentioned
   - "incident response" relates to P11 + P14 (security + communication)

4. **Deviation Consideration**: If deviation exists, ADD:
   - P17: Deficiency communication (always add for deviations)
   - P16: Ongoing evaluations (control testing revealed issue)
   - P10: Control activities (control effectiveness in question)

5. **Return 3-5 matches**:
   - Include all principles with confidence ≥ 0.6
   - Each match must address a DIFFERENT component or aspect
   - Prefer more comprehensive coverage over limiting to 3

Respond ONLY with JSON:
{{
  "matches": [
    {{
      "id": "COSO Principle ID (e.g., 11)",
      "confidence": 0.0-1.0,
      "component": "Control Environment|Risk Assessment|Control Activities|Information & Communication|Monitoring Activities",
      "keywords_matched": ["keyword1", "synonym1", "related_term1"],
      "aspect_addressed": "Which specific part of control this principle covers",
      "reasoning": "Specific explanation with semantic matches (100 chars max)"
    }}
  ]
}}

**Return 3-5 matches** (extend to 5 if multiple strong matches exist).
Include only matches with confidence ≥ 0.6.
Each match MUST have DISTINCT COSO principle ID and address a DIFFERENT aspect of the control.
IMPORTANT: Do not limit to 3 - return up to 5 matches if warranted.
If no good matches exist, return {{"matches": []}}.
"""

FRAMEWORK_CROSS_VALIDATION_PROMPT = """
You are an expert SOC 2 auditor validating framework alignment consistency.

Control Description:
{control_desc}

Top TSC Matches:
{tsc_matches}

Top COSO Matches:
{coso_matches}

## Validation Task:

Assess whether the selected TSC and COSO frameworks are mutually consistent for this control type.

## Expected Alignments:

**Strong Alignment** (both frameworks focus on same aspect):
- TSC CC1-CC5 + COSO P1-P5 (governance/environment)
- TSC CC6 + COSO P6-P9 (risk assessment)
- TSC CC7 + COSO P10-P12 (control activities)
- TSC CC8 + COSO P13-P15 (communication)
- TSC CC9 + COSO P16-P17 (monitoring)
- TSC C1.x (security) + COSO P11 (technology controls)
- TSC A1.x (availability) + COSO P10 or P11 (control activities/technology)

**Moderate Alignment** (related but not identical focus):
- TSC security (C1.x) + COSO P10 (general control activities)
- TSC domain-specific + COSO governance (P1-P5)

**Weak/Conflicting Alignment** (frameworks focus on different aspects):
- TSC governance (CC1-CC5) + COSO monitoring (P16-P17)
- TSC security (C1.x) + COSO communication (P13-P15)
- TSC risk (CC6) + COSO control activities (P10-P12)

## Output Requirements:

Respond ONLY with JSON:
{{
  "alignment_quality": "Strong|Moderate|Weak|Conflicting",
  "consistency_score": 0.0-1.0,
  "reasoning": "2-3 sentence explanation of alignment assessment",
  "flags": ["list", "of", "any", "concerns", "or", "misalignments"],
  "confidence_adjustments": {{
    "tsc_confidence_multiplier": 0.8-1.2,
    "coso_confidence_multiplier": 0.8-1.2,
    "justification": "Why confidence should be adjusted up or down"
  }}
}}

- alignment_quality: Overall coherence between TSC and COSO selections
- consistency_score: 0-1 score (1.0 = perfect alignment, 0.0 = completely misaligned)
- flags: Specific concerns (e.g., "TSC focuses on security but COSO on governance")
- confidence_adjustments: Multipliers to apply to original confidence scores (0.8 = reduce 20%, 1.2 = increase 20%)
"""

# Legacy GPT_PROMPTS dictionary for backward compatibility with CLI tools
# All production code should use the individual prompt constants defined above
GPT_PROMPTS = {
    'section_detection': SECTION_DETECTION_PROMPT,
    'extract_toc': EXTRACT_TOC_PROMPT,
    'section_heading_validation': SECTION_HEADING_VALIDATION_PROMPT,
    'extract_toc_headings_and_pages': EXTRACT_TOC_HEADINGS_AND_PAGES_PROMPT,
    'cuec_extraction': CUEC_EXTRACTION_PROMPT,
    'cuec_consolidation': CUEC_CONSOLIDATION_PROMPT,
    'executive_summary': EXECUTIVE_SUMMARY_PROMPT,
}

# --- Entity Extraction from Context Prompt ---
ENTITY_EXTRACTION_FROM_CONTEXT_PROMPT = """
You are an expert SOC 2 report analyst. Extract structured information for a {entity_type} from the provided text context.

## Search Term
{search_text}

## Text Context
The following context contains {occurrence_count} occurrence(s) of the search term. Page boundaries are marked with === PAGE X ===.

{text_context}

## Task
Extract the following fields based on the entity type:

### For entity_type="control":
- control_id: The control identifier (e.g., CC6.1, CC7.2)
- description: Full description of the control
- test_procedures: Testing procedures performed
- test_results: Results of testing
- deviation_description: Any deviations or exceptions noted
- page_ref: Page number where the control appears (from === PAGE X === markers)

### For entity_type="cuec":
- description: Description of the complementary user entity control
- tsc_id: TSC framework identifier
- coso_id: COSO framework identifier
- justification: Justification for the CUEC
- page_ref: Page number (from === PAGE X === markers)

### For entity_type="subservice_org":
- name: Name of the subservice organization
- description: Description of services provided
- page_ref: Page number (from === PAGE X === markers)

## Output Format
Return a JSON object with:
- The extracted fields for the entity type (use null for fields not found)
- confidence: 0.0-1.0 indicating extraction confidence

Example for control:
{{
  "control_id": "CC6.1",
  "description": "The entity implements logical access security...",
  "test_procedures": "We inspected system configurations...",
  "test_results": "No exceptions noted",
  "deviation_description": null,
  "page_ref": 42,
  "confidence": 0.95
}}

If the search term does not correspond to a valid {entity_type}, return confidence 0.0 and null for all fields except confidence.
"""
