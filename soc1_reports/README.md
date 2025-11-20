# SOC 1 Test Reports

This directory contains SOC 1 Type 2 test reports for validation and accuracy testing.

## Directory Structure

```
soc1_reports/
├── README.md (this file)
├── sample_reports/       # Sample SOC 1 reports for testing
├── baselines/            # Validation baselines (JSON snapshots)
└── validation_results/   # Test run outputs
```

## Adding Test Reports

1. Place SOC 1 Type 2 PDF reports in `sample_reports/`
2. Run validation scan to generate baseline
3. Baselines stored in `baselines/` with timestamp
4. Max 20 baselines retained (auto-cleanup oldest)

## Baseline Format

```json
{
  "report_name": "CompanyName_SOC1.pdf",
  "scan_date": "2025-01-15T10:30:00Z",
  "report_type": "SOC1",
  "controls_count": 45,
  "assertions_mapped": 18,
  "framework_breakdown": {
    "SOC1": 43,
    "AMBIGUOUS": 2,
    "PARTIAL_EXTRACTION": 0
  },
  "sample_controls": [...],
  "accuracy_metrics": {
    "assertion_precision": 0.95,
    "control_recall": 0.92
  }
}
```

## Validation UI

Access validation UI at:
```
http://localhost:3000/validation
```

Features:
- Side-by-side comparison of current vs baseline extractions
- Manual review and annotation of accuracy
- Framework category verification
- Financial assertion verification
- Batch reprocessing

## CI/CD Integration

Automated testing runs on:
- Pull requests to main/develop
- Nightly builds
- Manual trigger via GitHub Actions

Pass criteria:
- Control recall > 90%
- Assertion precision > 85%
- Zero PARTIAL_EXTRACTION flags
- < 5% AMBIGUOUS controls

## Notes

- Test reports should be anonymized or public domain
- Baselines versioned with extractor version numbers
- Regression detected if metrics drop > 5% from baseline
