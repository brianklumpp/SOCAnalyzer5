# Framework Mapping

## Overview

Framework mapping aligns extracted controls to Trust Services Criteria (TSC) and COSO 2013 Internal Control frameworks.

## Supported Frameworks

SOCAnalyzer supports dynamic framework mapping with 10+ frameworks:

### SOC 2 Frameworks
- **Trust Services Criteria (TSC)**: CC1.1 - CC9.1, A1.1 - A1.3, C1.1 - C1.2, PI1.1 - PI1.5, P1.1 - P8.1
- **COSO 2013 Internal Control**: 17 principles across 5 components (Control Environment, Risk Assessment, Control Activities, Information & Communication, Monitoring)
- **ISO 27001**: Information security controls
- **NIST Cybersecurity Framework**: Identify, Protect, Detect, Respond, Recover

### SOC 1 Frameworks
- **Financial Assertions**: Existence/Occurrence, Completeness, Rights/Obligations, Valuation/Allocation, Presentation/Disclosure
- **COSO Internal Control - Financial Reporting (ICFR)**: Same 17 principles as COSO 2013, focused on financial reporting
- **ISAE 3402**: International Standard for Assurance Engagements
- **CSAE 3416**: Canadian Standard on Assurance Engagements
- **AAF 01/06**: Australian Auditing Framework
- **GS 007**: German auditing standard

Framework selection is automatic based on report type (SOC1/SOC2/COMBINED).

## Extraction Methods

### Direct Extraction
GPT extracts criteria directly from control descriptions:
```
"TSC_criteria": ["CC6.1", "CC6.7"],
"COSO_criteria": ["10"]
```

### Pattern Matching
Fallback for missed criteria:
- Regex patterns for common formats
- Fuzzy matching for variations
- Context-based inference

### Manual Mapping
Users can:
- Add missing criteria
- Remove incorrect mappings
- Bulk edit criteria

## Mapping Rules

### TSC Mapping
- Multiple criteria per control supported
- Criteria stored as JSON array
- Validation against known criteria list

### COSO Mapping
- Principle numbers (1-17)
- Can map to multiple principles
- Component derived from principle number

## Coverage Calculation

### TSC Coverage
```
covered_criteria / total_criteria * 100
```
- Tracks which TSC criteria have controls
- Highlights gaps in coverage
- Supports audit planning

### COSO Coverage
```
covered_principles / 17 * 100
```
- Shows internal control completeness
- Identifies missing principles

## Visualization

### Coverage Charts
- Pie charts for overall coverage
- Bar charts by category
- Heatmaps for detailed view

### Gap Analysis
- Lists uncovered criteria
- Shows frequency of criteria usage
- Identifies over-tested areas

## Use Cases

### Audit Planning
- Identify untested criteria
- Plan test procedures
- Allocate audit resources

### Compliance Verification
- Ensure all required criteria tested
- Document control alignment
- Support regulatory requirements

### Report Quality
- Validate extraction accuracy
- Flag incomplete mappings
- Guide manual review

## Best Practices

1. **Review Automated Mappings**: Always verify GPT-extracted criteria
2. **Use Batch Edit**: Efficient for similar controls
3. **Check Coverage Reports**: Identify gaps early
4. **Document Deviations**: Note why criteria aren't covered
5. **Leverage Patterns**: Build pattern library for your org
