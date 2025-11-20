# Validation Baselines

This directory stores JSON snapshots of validated extraction results for regression testing.

## Baseline Naming Convention

```
{report_name}_{extractor_version}_{timestamp}.json
```

Example:
```
AcmeFinancial_SOC1_v4soc1_20250115_103045.json
```

## Baseline Lifecycle

1. **Creation**: Manual review + approval via validation UI
2. **Storage**: JSON file with complete extraction results
3. **Comparison**: Future runs compared against approved baseline
4. **Expiration**: Max 20 baselines per report (FIFO cleanup)

## Baseline Contents

- Full scan metadata (report_type, dates, company, auditor)
- All extracted controls with assertions
- Framework categories
- CUECs
- Subservice organizations
- Accuracy metrics from manual review

## Usage in CI/CD

GitHub Actions workflow loads latest baseline for each test report and compares:
- Control count delta
- Assertion mapping changes
- Framework category shifts
- Confidence score variations

Alerts trigger if metrics deviate > 5% from baseline.
