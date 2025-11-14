# SOCAnalyzer Combined Result JSON Field Mapping

This document provides a comprehensive mapping of all fields present in the `combined_result.json` file, including their types, example values, and notes on usage. This mapping is intended to guide database schema alignment and backend insert logic.

---

## Combined Result JSON: Field Mapping Table

| JSON Key                  | Type                | Example Value / Structure                                                                 | Notes / Usage                                                                                 |
|---------------------------|---------------------|-------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| auditor                   | string              | "Boulay PLLP"                                                                            | Name of the audit firm                                                                        |
| confidence                | float               | 0.9                                                                                       | Confidence score for extraction                                                               |
| source_section            | string              | "SECTION I. INDEPENDENT SERVICE AUDITOR’S REPORT"                                        | Section of the report where info was found                                                    |
| source_page               | int                 | 5                                                                                         | Page number in the PDF                                                                       |
| raw_gpt_responses         | list of strings     | ["{...}", "{...}"]                                                                       | List of JSON-encoded GPT responses                                                           |
| confirmation_explanation  | string              | "Fallback: Boulay PLLP is a reputable accounting firm..."                                 | Explanation for auditor confirmation                                                         |
| company                   | string              | "SimpleLegal, Inc."                                                                      | Company name (flat key)                                                                      |
| parent_company            | string              | "Onit, Inc."                                                                             | Parent company name (flat key)                                                               |
| controls                  | list of dicts       | [{...}, {...}, ...]                                                                       | List of control objects (see below for structure)                                            |
| cuecs                     | list of dicts       | [{...}, {...}, ...]                                                                       | List of CUEC objects (see below for structure)                                               |
| subservice_orgs           | list of dicts/str   | [{"third_party_name": ...}, ...] or ["AWS", ...]                                        | List of subservice orgs (may be dicts or strings)                                            |
| product                   | string              | "SimpleLegal Legal Spend and Matter Management Software System"                           | Product name (flat key)                                                                      |
| report_date               | string (ISO date)   | "2025-02-19"                                                                             | Date of the report                                                                           |
| start_date                | string (ISO date)   | "2024-01-01"                                                                             | Coverage period start date                                                                   |
| end_date                  | string (ISO date)   | "2024-12-31"                                                                             | Coverage period end date                                                                     |
| sections                  | list of dicts       | [{"snippet": ...}, ...]                                                                   | Extracted text sections (optional, for extracted_text)                                       |
| bad_chunks                | list                | [...]                                                                                     | List of bad chunks (may be under controls/cuecs/subservice_orgs or top-level)                |
| raw_gpt_response          | string              | "{...}"                                                                                   | Single GPT response (optional)                                                               |
| raw_gpt_responses         | list of strings     | ["{...}", ...]                                                                            | Multiple GPT responses (optional)                                                            |
| explanation               | string              | "The date the auditor signed the report is ..."                                           | Explanation for extracted field                                                              |
| rescued_chunk_count       | int                 | 10                                                                                        | Number of rescued chunks (optional)                                                          |
| unrecoverable_chunks      | list                | []                                                                                        | List of unrecoverable chunks (optional)                                                      |
| bad_chunk_rescue_report   | list                | []                                                                                        | Details on rescued bad chunks (optional)                                                     |
| confirmation_explanation  | string              | "Fallback: ..."                                                                           | Explanation for auditor confirmation                                                         |
| type                      | string              | "Type 2"                                                                                  | Report type                                                                                  |

### Nested Structures

#### controls (list of dicts)
| Field                | Type      | Example Value                                                      | Notes                                  |
|----------------------|-----------|--------------------------------------------------------------------|----------------------------------------|
| control_seq          | int       | 262                                                                | Sequence/order (optional)              |
| control_id           | string    | "A1.1.1"                                                          | Control identifier                     |
| control_desc         | string    | "SimpleLegal measures current usage..."                            | Control description                    |
| control_test         | string    | "Inspected the AWS dashboard..."                                   | Test procedure (optional)              |
| control_test_results | string    | "No exceptions noted."                                             | Test results (optional)                |
| control_page_ref     | int/null  | 43                                                                 | Page reference (optional)              |
| control_line_ref     | int/null  | 10                                                                 | Line reference (optional)              |
| control_gpt_opinion  | string    | ""                                                                 | GPT opinion (optional)                 |
| control_gpt_reasoning| string    | "Merged duplicate controls..."                                     | GPT reasoning (optional)               |

#### cuecs (list of dicts)
| Field                        | Type      | Example Value                  | Notes                                  |
|------------------------------|-----------|-------------------------------|----------------------------------------|
| cuec_id                      | string    | "CUEC-1"                      | CUEC identifier (may be missing)       |
| cuec_desc                    | string    | "Description of CUEC..."      | CUEC description (may be missing)      |
| cuec_distance_from_cuec_keywords | int   | 0                             | Distance metric (optional)             |

#### subservice_orgs (list)
| Field                | Type      | Example Value                  | Notes                                  |
|----------------------|-----------|-------------------------------|----------------------------------------|
| third_party_name     | string    | "AWS"                         | Name of subservice org                 |
| third_party_confidence | float   | 0.9                           | Confidence score (optional)            |
| (or just string)     | string    | "AWS"                         | Sometimes just a string                |

#### sections (list of dicts)
| Field    | Type   | Example Value         | Notes                       |
|----------|--------|----------------------|-----------------------------|
| snippet  | string | "Full extracted text"| Extracted text snippet      |

---

## Database Schema and Mapping

### Table: scan
| Column                  | Type           | Maps from JSON Key(s)           | Notes/Usage                                  |
|------------------------|----------------|----------------------------------|----------------------------------------------|
| id                     | int (PK)       |                                  | Auto-increment                               |
| company_id             | int            | (FK to company.id)               | Set after company insert                     |
| product                | string         | product                          |                                              |
| scan_date              | datetime       | (timestamp)                      | Use now or from scan_history                 |
| report_date            | datetime       | report_date                      | Parse ISO string                             |
| coverage_start         | datetime       | start_date                       | Parse ISO string                             |
| coverage_end           | datetime       | end_date                         | Parse ISO string                             |
| pdf_file               | LargeBinary    |                                  | (optional, not in JSON)                      |
| pdf_filename           | string         |                                  | (optional, not in JSON)                      |
| extracted_text         | text           | sections[0].snippet              | Use first section snippet if present         |
| result_json            | JSON           | (entire JSON)                    | Store full combined_result.json              |
| gpt_cost               | float          |                                  | (optional, not in JSON)                      |
| gpt_model              | string         |                                  | (optional, not in JSON)                      |
| estimated_time_seconds | float          |                                  | (optional, not in JSON)                      |

### Table: company
| Column          | Type      | Maps from JSON Key(s)   | Notes/Usage                  |
|----------------|-----------|-------------------------|------------------------------|
| id             | int (PK)  |                         | Auto-increment               |
| name           | string    | company                 |                              |
| parent_company | string    | parent_company          |                              |
| confidence     | int       | confidence              | (optional, may be float)     |
| scan_id        | int (FK)  | scan.id                 | Set after scan insert        |

### Table: product
| Column   | Type      | Maps from JSON Key(s)   | Notes/Usage                  |
|----------|-----------|-------------------------|------------------------------|
| id       | int (PK)  |                         | Auto-increment               |
| name     | string    | product                 |                              |
| scan_id  | int (FK)  | scan.id                 | Set after scan insert        |

### Table: control
| Column      | Type      | Maps from JSON Key(s)   | Notes/Usage                  |
|-------------|-----------|------------------------|------------------------------|
| id          | int (PK)  |                        | Auto-increment               |
| control_id  | string    | controls[].control_id   |                              |
| description | text      | controls[].control_desc |                              |
| scan_id     | int (FK)  | scan.id                | Set after scan insert        |

### Table: cuec
| Column      | Type      | Maps from JSON Key(s)   | Notes/Usage                  |
|-------------|-----------|------------------------|------------------------------|
| id          | int (PK)  |                        | Auto-increment               |
| cuec_id     | string    | cuecs[].cuec_id        |                              |
| description | text      | cuecs[].cuec_desc      |                              |
| scan_id     | int (FK)  | scan.id                | Set after scan insert        |

### Table: subservice_org
| Column     | Type      | Maps from JSON Key(s)           | Notes/Usage                  |
|------------|-----------|----------------------------------|------------------------------|
| id         | int (PK)  |                                  | Auto-increment               |
| name       | string    | subservice_orgs[].third_party_name or subservice_orgs[] (if str) |                              |
| confidence | int       | subservice_orgs[].third_party_confidence | (optional, may be float)     |
| scan_id    | int (FK)  | scan.id                          | Set after scan insert        |

### Table: scan_history
| Column    | Type      | Maps from JSON Key(s)   | Notes/Usage                  |
|-----------|-----------|------------------------|------------------------------|
| id        | int (PK)  |                        | Auto-increment               |
| timestamp | datetime  | (now)                  |                              |
| filename  | string    |                        |                              |
| results   | JSON      | (entire JSON)          | Store full combined_result.json |

---

## Mapping Notes
- All date fields in JSON are ISO 8601 strings and must be parsed to datetime for DB.
- Some fields (e.g., confidence) may be float in JSON but int in DB; consider updating DB to float for precision.
- For subservice_orgs, if the entry is a string, use as name; if dict, use third_party_name and third_party_confidence.
- The insert logic should check for both flat and nested (legacy) keys for all entities.
- Any fields in JSON not mapped to a DB column can be stored in result_json for reference.

---

This table should be used as the source of truth for aligning your database schema and backend insert logic with the JSON extraction output.
