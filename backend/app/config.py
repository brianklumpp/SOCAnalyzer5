# --- All imports at the top (PEP8 best practice) ---
import os
import pathlib

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

# Example prompts for GPT inquiries
GPT_PROMPTS = {
    'summary': "Summarize the key findings in the SOC report.",
    'controls': "List all control activities described in the SOC report.",
    'exceptions': "Identify any exceptions or issues noted in the SOC report.",
    'section_detection': (
        "You are an expert at analyzing SOC reports. Given the full text of a SOC report, your task is to:\n"
        "1. Analyze the table of contents and the document to estimate the best probable start position (character offset and percentage) for each of the following section topics: {section_keys}.\n"
        "2. Do NOT simply use the first keyword match. Instead, use the table of contents to estimate the page number, then analyze the content before and after that position to find the best section start.\n"
        "3. For each section, output an object with these keys:\n"
        "   - topic (string)\n   - offset (integer, character offset)\n   - percent (float, 0-100)\n   - confidence (probability percentage, 0-100)\n"
        "4. Output a single valid JSON array (list of objects, one per section). Do not include any explanation, markdown, or extra text. Only output the JSON array.\n\n"
        "SOC Report Text:\n{text}\n"
    ),
    'extract_toc': (
        "You are an expert at reading SOC reports. Given the first part of a SOC report, extract ONLY the Table of Contents section. "
        "Return the Table of Contents as plain text, exactly as it appears in the report. If no TOC is found, reply with 'TOC NOT FOUND'.\n\n"
        "Report Text:\n{text}\n"
    ),
    'section_heading_validation': (
        "You are analyzing a document. Given the following text, does the line marked with >>> look like a section heading?\n"
        "Respond with 'Yes' or 'No' and a brief reason.\n"
        "Context:\n{text}\n>>> {line}\n"
    ),
    'section_chunk_scan': (
        "You are analyzing a SOC report. The following chunk of text is from the report, starting at line {start_line} of the full document. "
        "Does this chunk contain the start of the section titled '{heading}'? "
        "Only consider a heading if it appears on its own line, not as part of a paragraph. "
        "If yes, reply 'Yes, absolute line X: [exact heading text]' where X is the line number in the full document (not just this chunk) and [exact heading text] is the heading as it appears. "
        "If not, reply 'No, does not contain section start.'\n\nChunk:\n{chunk}"
    ),
    'extract_toc_headings_and_pages': (
        "Given the following Table of Contents, extract all MAIN section headings (not sub-entries) "
        "and their page numbers. Respond ONLY with a JSON array of objects with 'heading' and 'page' fields. "
        "Do not include sub-entries or subsections. Example output: "
        "[{{\"heading\": \"Section I – Assertion of Management\", \"page\": 1}}, {{\"heading\": \"Section II – Service Auditor's Report\", \"page\": 3}}]" 
        "\n\nTOC:\n{toc_text}"
    ),
}

# Prompt for extracting the auditor firm from the auditor section
AUDITOR_EXTRACTION_PROMPT = (
    "You are an expert at reading SOC 2 reports. Given the following text from the Service Auditor's Report section (and page 1), extract the name of the auditing firm that performed the SOC 2 examination. "
    "Return a JSON object with these keys: 'auditor' (the firm name as it appears in the text), 'confidence' (0-1, your confidence in the extraction), and 'explanation' (brief reasoning). "
    "If you cannot find the auditor, set 'auditor' to null and confidence to 0.\n\nText:\n{text}\n"
)

# Enhanced prompt for auditor extraction, excluding company and parent company
AUDITOR_EXTRACTION_PROMPT_EXCLUDE = (
    "You are an expert at reading SOC 2 reports. Given the following text from the Service Auditor's Report section (and page 1), extract the name of the auditing firm that performed the SOC 2 examination. "
    "{company_line}"
    "Do NOT return the company being audited or its parent/owner as the auditor. "
    "Return a JSON object with these keys: 'auditor' (the firm name as it appears in the text, excluding the company and parent), 'confidence' (0-1, your confidence in the extraction), and 'explanation' (brief reasoning). "
    "If you cannot find the auditor, set 'auditor' to null and confidence to 0.\n\nText:\n{text}\n"
)

# Prompt for extracting the company being audited and any parent company
COMPANY_EXTRACTION_PROMPT = (
    "You are an expert at reading SOC 2 reports. Given the following text, extract the name of the company (legal entity) being audited, and if present, the name of any parent or owner company (e.g., 'an Onit, Inc. company' or similar). "
    "Return a JSON object with these keys: 'company' (the company name as it appears in the text, always present), 'parent_company' (the parent/owner company name, or null if not found), 'confidence' (0-1, your confidence in the extraction), and 'explanation' (brief reasoning). "
    "If you cannot find a parent company, set 'parent_company' to null.\n\nText:\n{text}\n"
)

# Prompt for extracting the product/service/system being audited
PRODUCT_EXTRACTION_PROMPT = (
    "You are an expert at reading SOC 2 reports. Given the following text, extract the name of the product, service, or system being audited (e.g., 'Experience Cloud', 'Okta Identity as a Service', etc.). "
    "Return a JSON object with these keys: 'product' (the product/service/system name as it appears in the text), 'confidence' (0-1, your confidence in the extraction), and 'explanation' (brief reasoning). "
    "If you cannot find the product/service/system, set 'product' to null and confidence to 0.\n\nText:\n{text}\n"
)

# Prompt for extracting the report date
REPORT_DATE_EXTRACTION_PROMPT = (
    "You are an expert at reading SOC 2 reports. Given the following text from the end of the Service Auditor's Report section, what is the date the auditor signed the report? "
    "Return the date as 'YYYY-MM-DD' if possible, or null if not found. Respond as JSON: {{ 'report_date': 'YYYY-MM-DD' or null, 'explanation': '...' }}\n\nText:\n{text}"
)

# Prompt for extracting the coverage period
COVERAGE_PERIOD_EXTRACTION_PROMPT = (
    "You are an expert at reading SOC 2 reports. Given the following text from the beginning of the Service Auditor's Report section, extract the coverage period. "
    "If the report is Type 2, return the start and end dates of the period (e.g., '2023-01-01' to '2023-12-31'). If Type 1, return only the as-of date as the end date, and set start date to null. "
    "Respond as JSON: {{ 'type': 'Type 1' or 'Type 2', 'start_date': 'YYYY-MM-DD' or null, 'end_date': 'YYYY-MM-DD' or null, 'explanation': '...' }}\n\nText:\n{text}"
)


# Path to .env file for API key
ENV_PATH = str(PROJECT_ROOT / '.env')

# Default model to use
DEFAULT_GPT_MODEL = 'gpt-4o'

# Default generation parameters
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TOP_P = 0.0  # Set to 0.0 for maximum determinism and minimal hallucination

# --- Advanced GPT Token & Chunk Management ---
CHARS_PER_TOKEN = 3.5  # Average chars per token for planning purposes

# Token Management
MAX_TOTAL_TOKENS = 4096  # GPT-3.5's context window
MAX_OUTPUT_TOKENS = 1000  # Maximum reasonable response
MAX_INPUT_TOKENS = MAX_TOTAL_TOKENS - MAX_OUTPUT_TOKENS  # Available for input

# Token Budget Allocations
GPT_SYSTEM_TOKENS = 400   # System prompts and instructions
GPT_USER_TOKENS = 400     # User prompts and queries
GPT_RESPONSE_TOKENS = 500 # Default expected response size
GPT_AVAILABLE_TOKENS = (
    MAX_TOTAL_TOKENS 
    - GPT_SYSTEM_TOKENS 
    - GPT_USER_TOKENS 
    - GPT_RESPONSE_TOKENS
)

# Content Chunking Strategy
DEFAULT_CHUNK_SIZE = int(GPT_AVAILABLE_TOKENS * CHARS_PER_TOKEN * 0.4)  # 40% of available space
PRIMARY_CHUNK_SIZE = int(GPT_AVAILABLE_TOKENS * CHARS_PER_TOKEN * 0.6)  # 60% of available space for critical fields
DESCRIPTION_CHUNK_SIZE = int(GPT_AVAILABLE_TOKENS * CHARS_PER_TOKEN * 0.4)  # 40% of available space
SUBSERVICE_CHUNK_SIZE = int(GPT_AVAILABLE_TOKENS * CHARS_PER_TOKEN * 0.3)  # 30% of available space
MAX_CHUNK_SIZE = int(MAX_INPUT_TOKENS * CHARS_PER_TOKEN * 0.8)  # 80% of max input tokens for safety

# Total Combined Text Limits
TOTAL_PRIMARY_SIZE = PRIMARY_CHUNK_SIZE * 3  # Allow for multiple primary sections
TOTAL_DESCRIPTION_SIZE = DESCRIPTION_CHUNK_SIZE * 3  # Allow for multiple description sections
TEXT_OVERLAP = 1000  # Characters of overlap between chunks for context preservation

# Configuration for GPT models
GPT_MODELS = {
    'control_extractor': 'gpt-4o',
    'control_extractor_v2': 'gpt-4o',
    'company_extractor': 'gpt-3.5-turbo',
    'auditor_extractor': 'gpt-3.5-turbo',
    'product_extractor': 'gpt-3.5-turbo',
    'report_date_extractor': 'gpt-3.5-turbo',
    'coverage_period_extractor': 'gpt-3.5-turbo',
    'cuec_extractor': 'gpt-3.5-turbo',
    'subservice_orgs_extractor': 'gpt-3.5-turbo'
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
    'gcp': 'Google Cloud Platform',
    'google cloud platform': 'Google Cloud Platform',
    'microsoft azure': 'Microsoft Azure',
    'azure': 'Microsoft Azure',
    'ibm cloud': 'IBM Cloud'
    # Add more as needed
}

SO_KEYWORDS = ["subservice", "subservice organization"]

SUBSERVICE_ORG_GPT_FILTER_PROMPT = (
    "You are reviewing extracted third-party entities from a SOC 2 report. "
    "For each entry, answer: Is this an actual service offering or cloud provider? Keep service offerings and cloud providers (like AWS, Azure, GCP, etc.)."
    "If not, specify what it is (framework, department, generic term, software, OS, component, etc.). "
    "Exclude any entries that are frameworks, standards, open-source projects, software, operating systems, or elements within a cloud provider (e.g., Amazon Linux 2, Ubuntu, React, OWASP, Kubernetes, NIST, ISO, etc.). "
    "Return a JSON object with: 'keep' (true/false), 'type' (company/framework/software/OS/component/department/etc.), 'reason' (why keep or exclude), and 'entry' (the original dict).\n"
    "\nContext from the report:\n{context}\n"
    "\nExample input:\nName: Linux\nDescription: Operating System\n\nExample output:\n{{\"keep\": false, \"type\": \"OS\", \"reason\": \"This is an operating system, not a company.\", \"entry\": ... }}\n\nNow review this entry:\nName: {name}\nDescription: {desc}"
)

SUBSERVICE_ORG_ADVANCED_EXTRACTION_PROMPT = (
    "You are an expert at reading SOC 2 reports. Given the following text from the Description of System section, identify all third parties (companies, cloud providers, vendors, etc.) mentioned.\n"
    "For each third party, research what they do and fill out the following fields as JSON objects in a list, using this exact format for each object:\n"
    "{{\n"
    "  \"third_party_name\": <string>,\n"
    "  \"third_party_description\": <string>,\n"
    "  \"third_party_page_ref\": <string>,\n"
    "  \"third_party_confidence\": <float>,\n"
    "  \"distance_from_so_keywords\": <int>,\n"
    "  \"likely_so\": <\"Yes\" or \"No\">,\n"
    "  \"common_so\": <\"Yes\" or \"No\">,\n"
    "  \"third_party_controls\": [\n"
    "    {{\n"
    "      \"third_party_control_seq\": <int>,\n"
    "      \"third_party_control_id\": <string or null>,\n"
    "      \"third_party_control_desc\": <string or null>\n"
    "    }}\n"
    "    // ...repeat for each control...\n"
    "  ]\n"
    "}}\n"
    "- Only include actual third-party service providers, not internal teams, departments, frameworks, generic terms, or software installed locally (e.g., Windows, Office, Linux, etc.).\n"
    "- Do not include generic terms like 'third-party vendor', 'consulting partners', 'Open Web Application Security Project (OWASP)', or internal company teams.\n"
    "- If you cannot find a value, use null. Output a single JSON array (list of objects, one per third party), and do not include any explanation, markdown, or extra text.\n\nText:\n{text}\n"
)

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

CUEC_EXTRACTION_PROMPT = (
    "You are an expert at reading SOC 2 reports. Given the following text from the Description of System section, extract only explicit Complementary User Entity Controls (CUECs) or customer/user entity responsibilities.\n"
    "A valid CUEC must explicitly state responsibility to the user entity, customer, or client. Not just assign responsibility.\n"
    "Only include controls that use clear responsibility language such as: 'user entity is responsible for...', 'customer must...', 'user must...', 'user entities are required to...', etc.\n"
    "Do NOT include product features, internal controls, or vague statements unless they clearly assign responsibility to the user entity.\n"
    "If a control assigns responsibility to the {company_names} (e.g., '{company_names} is responsible for...'), or {parent_company_names}, DO NOT include it as a CUEC.\n"
    "For each CUEC, return a JSON object with these fields:\n"
    "cuec_tsc_id: (string or null, the TSC ID if present),\n"
    "cuec_description: (string, the CUEC control requirement/description),\n"
    "cuec_line_ref: (integer, the line number in the text where the CUEC was found/extracted),\n"
    "cuec_gpt_opinion: (Yes or No, does it sound like a CUEC?),\n"
    "cuec_gpt_responsibility_phrase: (string, the exact phrase from the text that assigns responsibility to the user entity, or null if not found),\n"
    "cuec_gpt_reasoning: (string, a concise explanation of why you classified this as a CUEC or not, and any relevant context or clues from the text),\n"
    "cuec_framework_alignment: (string, does this CUEC align to the COSO Internal Control Framework, AICPA Trust Services Criteria, both, or neither? Respond with 'COSO', 'AICPA_TSC', 'COSO or AICPA_TSC', or 'Undetermined'),\n"
    "cuec_framework_alignment_id: (string or null, the COSO or AICPA TSC ID it aligns to, or null if undetermined),\n"
    "cuec_justification: (string, your justification for the framework alignment and ID),\n"
    "If you cannot find a value, use null.\n"
    "For every control or responsibility statement in the text that you do NOT include as a CUEC, output a JSON object in a separate array called 'excluded', with these fields: 'excluded_description', 'excluded_reason'.\n"
    "Output a JSON object with two arrays: 'cuecs' (list of included CUECs as above), and 'excluded' (list of excluded controls with reasons). Do not include any explanation, markdown, or extra text.\n\nText:\n{text}\n"
)

CUEC_CONSOLIDATION_PROMPT = (
    "You are an expert at reading SOC 2 reports. Given the following extracted Complementary User Entity Controls (CUECs), consolidate and deduplicate the results.\n"
    "For each unique CUEC, merge similar or duplicate controls (based on description and TSC ID). For each CUEC, provide a cuec_gpt_reasoning field with a concise explanation of why you merged or kept it, and any relevant context.\n"
    "Output a single JSON array, one object per CUEC, with these fields: cuec_seq, cuec_tsc_id, cuec_description, cuec_line_ref, cuec_confidence, cuec_gpt_opinion, cuec_distance_from_cuec_keywords, cuec_gpt_reasoning, cuec_framework_alignment, cuec_framework_alignment_id, cuec_justification.\n"
    "Do not include any explanation, markdown, or extra text.\n\nExtracted CUECs:\n{cuecs}\n"
)

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
Your task is to extract detailed control information from the provided text and return it in JSON format. The text is structured in sections, 
and your focus should be on identifying and extracting specific elements related to a control. Follow the 
instructions carefully to ensure accurate extraction without inferring any information not explicitly stated in 
the text.

Instructions:

1. Identify Control IDs for a Single Control:
   - Look for one or more control IDs, which may appear as random strings of letters, numbers, periods, dashes, 
   or TSC IDs.
   - Control IDs are unique identifiers for the control and are usually followed by a description.
   - If you find multiple control IDs separated by descriptive text, you should only extract the first set.  The
   next set of IDs will be for either a different control or other references which may be used later for 
   another purpose.

2. Extract Control Description:
   - Identify and extract 1-5 sentences or a bulleted list that describes the control. Usually follows the control ID.
   - The description should provide a clear understanding of the control's purpose and implementation.

3. Identify Additional Control References:
   - Look for one or more additional reference strings related to the control, such as series of digits or strings.
   - These references are usually separated by text from the control IDs or control description and may appear 
   in different parts of the text.

4. Extract Comments on Testing:
   - Identify sentences that describe what was tested, examined, viewed, or reviewed.
   - These comments provide insight into the testing process and methodology.

5. Extract Test Results:
   - Look for statements indicating test results, such as notes on deviations, findings, gaps, or errors.
   - If no deviations or errors are found, note the absence of such findings.
   - This is usually the last section of the control section.  Anything after this is either not part of the control, 
   is a different control, or is a different section of the report.  Do not include anything after this as it will 
   likely be extracted as part of the next chunk of content being processed.

6. Provide the Ending Line Number:
   - After extracting the control information, provide the line number where this control information ends.
   - This will be used to determine the starting position for the next chunk.

7. Provide an Initial Confidence Score and Justification:
   - Provide a confidence score between 0 and 1 indicating how confident you are that the extracted information represents a control.
   - Include a brief justification for your confidence score, explaining why you believe this is a control.

Return the extracted information in the following JSON format:
{{
    "control_id": "",
    "control_desc": "",
    "control_test": "",
    "control_test_results": "",
    "additional_references": [],
    "end_line": 0,
    "control_confidence": 0.0,
    "control_gpt_conf_justification": ""
}}

Text to analyze (starting at line {start_line}):
{text}
"""

# Prompt for consolidating and deduplicating extracted controls
CONTROL_CONSOLIDATION_PROMPT = (
    "You are an expert at reading SOC 2 reports. Given the following extracted controls, consolidate and deduplicate the results.\n"
    "For each unique control, merge similar or duplicate controls (based on description and control ID). For each control, provide a control_gpt_reasoning field with a concise explanation of why you merged or kept it, and any relevant context.\n"
    "Output a single JSON array, one object per control, with these fields: control_seq, control_id, control_desc, control_test, control_test_results, control_page_ref, control_line_ref, control_gpt_opinion, control_gpt_reasoning.\n"
    "Do not include any explanation, markdown, or extra text.\n\nExtracted Controls:\n{controls}\n"
)

# Refine CHUNK_ANALYSIS_PROMPT to emphasize using content directly from the text

CHUNK_ANALYSIS_PROMPT = """
You are analyzing a section of a SOC report. Your task is to identify logical breakpoints in the text where control sections start and end. Use only the information provided in the text and do not infer or assume additional details. Look for patterns such as control IDs, descriptions, test procedures, and results. Provide a list of character positions in the text where these breakpoints occur.
"""

# Refine SEGMENT_CLASSIFICATION_PROMPT to emphasize using content directly from the text

SEGMENT_CLASSIFICATION_PROMPT = """
You are analyzing a section of a SOC report. Your task is to classify each segment of text into one of the following categories: control ID, control description, test procedure, test result. Use only the information provided in the text and do not infer or assume additional details. Provide a structured representation of the classified segments.
"""

DYNAMIC_CHUNKING_PROMPT = (
    "Identify the single numeric character position in the text where each control section header starts. "
    "Do not infer or assume any details not present in the text."
)

SEGMENT_CLASSIFICATION_PROMPT = (
    "You are an expert at analyzing SOC reports. Given the following text, classify each segment as 'control_id', 'control_description', 'test_procedure', or 'test_result'. "
    "Return a JSON array of objects, each with keys: 'type' and 'text'. "
    "If no segments are found, return an empty array."
)

# Model-specific settings
GPT_MODEL_SETTINGS = {
    'gpt-4o': {
        'max_tokens': 4096,
        'temperature': 0,
        'top_p': 0
    },
    'gpt-3.5': {
        'max_tokens': 2048,
        'temperature': 0,
        'top_p': 0
    }
}

# --- Control Extraction Testing Config ---
CONTROL_TESTING_ENABLED = True  # Set to False to disable test mode and process the full file
CONTROL_TESTING_MAX_LINE = 2000  # Only process up to this line number when testing is enabled