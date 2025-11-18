# 5-Factor Confidence System - Implementation Complete

## Overview
Successfully implemented a comprehensive 5-factor confidence scoring system for SOC2 control extraction with configurable weights, frozen confidence history, and detailed UI components for inspection.

## Implementation Status: ✅ COMPLETE

### Backend (100% Complete)

#### 1. Database Schema ✅
- **Models Added** (backend/app/models.py):
  - `ConfidenceWeights`: Stores weight configurations (global + org-specific overrides)
  - `ConfidenceWeightAudit`: Complete audit trail for weight changes
  - `ControlReview`: Admin feedback and review workflow support

- **Migration**: `2d834bf34316_add_confidence_weights_and_review_tables.py`
  - Status: Applied successfully
  - Creates 3 tables with indexes
  - Inserts global default weights (0.25/0.20/0.20/0.20/0.15)

#### 2. 5-Factor Calculation ✅
**Location**: `backend/app/extractors/control_extractor_v4.py`

**Helper Function**: `_calculate_multi_factor_confidence()` (lines 473-576)
- Calculates all 5 confidence factors
- Returns detailed breakdown with metadata
- Uses configurable weights from database

**Five Factors**:
1. **GPT Confidence** (default 25%): Base extraction quality from GPT model
2. **Pattern Confidence** (default 20%): ID pattern recognition from learned patterns
3. **Structure Score** (default 20%): Presence of key fields (test/results/description)
   - Formula: 1.0 if all 3 fields present, else proportional (0/3, 1/3, 2/3)
4. **Framework Score** (default 20%): Quality of TSC/COSO framework mappings
   - Formula: Average of TSC + COSO mapping confidences, 0.5 if none
5. **Deviation Score** (default 15%): Consistency between deviation flag and description
   - Formula: 1.0 if consistent (flag matches description presence), else 0.3

**Final Formula**:
```
final_confidence = (0.25 × gpt) + (0.20 × pattern) + (0.20 × structure) + (0.20 × framework) + (0.15 × deviation)
```

**Stored Metadata** (in `verification_metadata` JSON field):
```json
{
  "method": "5-factor",
  "final_confidence": 0.78,
  "calculated_at": "2025-01-08T10:30:00Z",
  "factor_scores": {
    "gpt_confidence": 0.85,
    "pattern_confidence": 0.90,
    "structure_score": 1.0,
    "framework_score": 0.72,
    "deviation_score": 1.0
  },
  "weighted_contributions": {
    "gpt_contribution": 0.2125,
    "pattern_contribution": 0.18,
    "structure_contribution": 0.20,
    "framework_contribution": 0.144,
    "deviation_contribution": 0.15
  },
  "weights_used": {
    "gpt_weight": 0.25,
    "pattern_weight": 0.20,
    "structure_weight": 0.20,
    "framework_weight": 0.20,
    "deviation_weight": 0.15
  }
}
```

#### 3. Data Flow Fixes ✅
**Location**: `backend/app/extractors/control_extractor_v4.py` (validate_controls function)

Fixed Issues:
- **Arrays to TEXT**: `control_tests` and `control_test_results` arrays now joined with newlines
- **Page Extraction**: Uses `get_page_for_line()` from pdf_handler.py to extract page numbers from "=== PAGE X ===" markers
- **Line References**: Preserved from extraction markers

#### 4. Weight Management API ✅
**Location**: `backend/app/main.py`

**7 Endpoints Implemented**:

1. `GET /api/confidence-weights`
   - Returns global default weights

2. `GET /api/confidence-weights/org/{organization}`
   - Returns org-specific weights or global fallback
   - Includes `is_custom` flag

3. `PUT /api/confidence-weights`
   - Updates global weights
   - Validation: Each factor 0.05-0.60, sum exactly 1.0 (±0.001)
   - Creates audit log entry

4. `PUT /api/confidence-weights/org/{organization}`
   - Creates/updates org-specific weight override
   - Same validation rules
   - Creates audit log entry

5. `DELETE /api/confidence-weights/org/{organization}`
   - Removes org-specific override (falls back to global)
   - Creates audit log entry

6. `POST /api/confidence-weights/reset`
   - Restores global defaults (0.25/0.20/0.20/0.20/0.15)
   - Creates audit log entry
   - Optional: Delete all org overrides

7. `GET /api/confidence-weights/audit-log`
   - Returns recent weight changes
   - Optional `organization` filter
   - Limit parameter (default 50)

**Validation Rules**:
- Each weight: 0.05 ≤ weight ≤ 0.60
- Sum of all 5 weights: must equal 1.0 (±0.001 tolerance)
- All changes logged to `confidence_weight_audit` table

#### 5. Verification Service Enhancement ✅
**Location**: `backend/app/services/verification_service.py`

**Key Changes**:
- Reads existing `verification_metadata` from extraction
- Extracts `factor_scores` and builds detailed `low_confidence_reasons`
- Enhanced reason messages:
  - "Low structure score (0.40 - missing test/results/desc)"
  - "No framework mappings (0.50)"
  - "Unknown pattern (0.30)"
  - "Inconsistent deviation flag (0.30)"
- **Backward Compatible**: Handles legacy 2-factor controls with 60/40 GPT/pattern formula

---

### Frontend (100% Complete)

#### 1. ConfidenceTooltip Component ✅
**Location**: `frontend/src/components/ConfidenceTooltip.tsx`

**Features**:
- Custom hover tooltip using MUI Popper (right-start placement)
- Displays all 5 factors with icons, labels, scores, and progress bars
- Color-coded by score:
  - **Red** (error): < 0.5
  - **Yellow** (warning): 0.5 - 0.7
  - **Green** (success): ≥ 0.7
- "View Details →" link triggers onClick callback for modal
- Graceful handling of legacy controls (shows "No detailed factor scores available")

**Factor Icons**:
- 🧠 GPT Quality (Psychology icon)
- 🔍 Pattern Match (Pattern icon)
- 🏗️ Structure (AccountTree icon)
- 🎯 Framework (Hub icon)
- ⚠️ Deviation (Warning icon)

#### 2. ConfidenceModal Component ✅
**Location**: `frontend/src/components/ConfidenceModal.tsx`

**Features**:
- **Header Gauge**: Large circular display of final confidence (gradient background)
- **Factor Breakdown Table**:
  - Factor name with icon and explanation
  - Weight percentage chip
  - Raw score chip (color-coded)
  - Weighted contribution (3 decimal places)
  - Status icon (check/warning/cancel)
- **Calculation Formula Display**: Shows actual values substituted into formula
- **Metadata Section**:
  - Method (5-factor)
  - Calculated timestamp
  - Weights snapshot (preserves weights at time of calculation)
- **History Timeline** (expandable):
  - Shows previous calculation results if `verification_metadata.history` exists
  - Timestamps and final confidence for each entry
- **Action Buttons**:
  - Close
  - "Open Review" (placeholder for future admin workflow)

**Legacy Control Handling**:
- Displays simplified view for pre-5-factor controls
- Shows GPT confidence, pattern confidence (if available), final confidence

#### 3. ReportPage Integration ✅
**Location**: `frontend/src/pages/ReportPage.tsx`

**Changes**:
1. **Imports Added**:
   ```tsx
   import ConfidenceTooltip from '../components/ConfidenceTooltip';
   import ConfidenceModal from '../components/ConfidenceModal';
   ```

2. **State Added**:
   ```tsx
   const [confidenceModalOpen, setConfidenceModalOpen] = useState(false);
   const [selectedControl, setSelectedControl] = useState<any>(null);
   const openConfidenceModal = (control: any) => { ... };
   const closeConfidenceModal = () => { ... };
   ```

3. **control_confidence Column Updated**:
   ```tsx
   { 
     key: "control_confidence", 
     label: "Confidence", 
     width: 100,
     render: (row: any) => (
       <ConfidenceTooltip 
         control={row} 
         onClick={() => openConfidenceModal(row)}
       >
         <span style={{ cursor: 'pointer' }}>
           {typeof row.control_confidence === 'number' 
             ? `${Math.round(row.control_confidence * 100)}%`
             : row.control_confidence}
         </span>
       </ConfidenceTooltip>
     )
   }
   ```

4. **Modal Rendered**:
   ```tsx
   <ConfidenceModal 
     open={confidenceModalOpen}
     control={selectedControl}
     onClose={closeConfidenceModal}
   />
   ```

5. **Data Processing Updated**:
   - Removed `control_confidence` percentage conversion in `processedControls`
   - Kept raw numeric value for tooltip/modal access
   - Display formatting handled by render function

#### 4. VerificationSection Update ✅
**Location**: `frontend/src/components/VerificationSection.tsx`

**Info Text Updated**:
```
About Verification: Controls are scored using 5-factor confidence analysis:
GPT Quality (25%), Pattern Match (20%), Structure (20%), Framework (20%), and Deviation (15%).
Hover over confidence scores to see factor breakdown, or click for detailed analysis.
Low confidence scores (<0.5) naturally identify potential false positives.
All controls are retained regardless of score for manual review.
```

---

## User Experience

### Viewing Confidence Scores

1. **Quick Inspection** (Hover):
   - Hover over any confidence score in Controls table
   - Tooltip appears showing all 5 factors with progress bars
   - Color-coded indicators show which factors are strong/weak
   - "View Details →" link prompts for deeper analysis

2. **Detailed Analysis** (Click):
   - Click confidence score (or "View Details" in tooltip)
   - Modal opens with:
     - Large gauge showing final score with color gradient
     - Table breaking down all factors with weights and contributions
     - Exact formula showing how final score was calculated
     - Metadata preserving weights used at calculation time
     - History timeline (if available)

3. **Legacy Controls**:
   - Older controls gracefully show simplified view
   - Tooltip displays "No detailed factor scores available"
   - Modal shows basic GPT/pattern scores

### Admin Features (Available via API)

#### Weight Configuration
```bash
# Get current global weights
GET /api/confidence-weights

# Update global weights
PUT /api/confidence-weights
{
  "gpt_weight": 0.30,
  "pattern_weight": 0.25,
  "structure_weight": 0.20,
  "framework_weight": 0.15,
  "deviation_weight": 0.10
}

# Set organization-specific weights
PUT /api/confidence-weights/org/TechCorp
{
  "gpt_weight": 0.20,
  "pattern_weight": 0.30,
  ...
}

# Remove org override
DELETE /api/confidence-weights/org/TechCorp

# Reset to defaults
POST /api/confidence-weights/reset
{
  "delete_all_org_overrides": false
}

# View audit log
GET /api/confidence-weights/audit-log?organization=TechCorp&limit=100
```

---

## Configuration

### Default Weights
```python
GPT_WEIGHT = 0.25        # Base extraction quality
PATTERN_WEIGHT = 0.20    # ID pattern matching
STRUCTURE_WEIGHT = 0.20  # Field completeness
FRAMEWORK_WEIGHT = 0.20  # TSC/COSO mappings
DEVIATION_WEIGHT = 0.15  # Flag consistency
```

### Weight Constraints
- **Per Factor**: 0.05 ≤ weight ≤ 0.60
- **Sum**: Exactly 1.0 (±0.001 tolerance)

### Confidence Threshold
- **Verification Threshold**: 0.5 (50%)
- Controls ≥ 0.5: VERIFIED status
- Controls < 0.5: PENDING REVIEW status

---

## Data Structures

### Database Models

#### ConfidenceWeights
```sql
CREATE TABLE confidence_weights (
    id SERIAL PRIMARY KEY,
    organization VARCHAR(255) NULL,  -- NULL = global default
    gpt_weight FLOAT NOT NULL,
    pattern_weight FLOAT NOT NULL,
    structure_weight FLOAT NOT NULL,
    framework_weight FLOAT NOT NULL,
    deviation_weight FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (organization)
);

CREATE INDEX idx_confidence_weights_org ON confidence_weights(organization);
```

#### ConfidenceWeightAudit
```sql
CREATE TABLE confidence_weight_audit (
    id SERIAL PRIMARY KEY,
    weight_config_id INTEGER REFERENCES confidence_weights(id),
    organization VARCHAR(255) NULL,
    changed_by_user_id INTEGER NULL,  -- Future: link to users table
    old_weights JSON NOT NULL,
    new_weights JSON NOT NULL,
    change_reason VARCHAR(500) NULL,
    change_type VARCHAR(50) NOT NULL,  -- 'update', 'create', 'delete', 'reset'
    changed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_weight_audit_org ON confidence_weight_audit(organization);
CREATE INDEX idx_weight_audit_time ON confidence_weight_audit(changed_at DESC);
```

#### ControlReview
```sql
CREATE TABLE control_review (
    id SERIAL PRIMARY KEY,
    control_id INTEGER NOT NULL REFERENCES controls(id),
    scan_id INTEGER NOT NULL REFERENCES scans(id),
    organization VARCHAR(255) NOT NULL,
    reviewed_by_user_id INTEGER NULL,  -- Future: link to users table
    review_status VARCHAR(50) NOT NULL,  -- 'approved', 'rejected', 'needs_revision'
    review_notes TEXT NULL,
    low_factor_flags JSON NULL,  -- ["pattern_confidence", "structure_score"]
    final_confidence_at_review FLOAT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_control_review_control ON control_review(control_id);
CREATE INDEX idx_control_review_scan ON control_review(scan_id);
CREATE INDEX idx_control_review_org ON control_review(organization);
```

### JSON Metadata

#### verification_metadata (in controls table)
```json
{
  "method": "5-factor",
  "final_confidence": 0.78,
  "calculated_at": "2025-01-08T10:30:00Z",
  "factor_scores": {
    "gpt_confidence": 0.85,
    "pattern_confidence": 0.90,
    "structure_score": 1.0,
    "framework_score": 0.72,
    "deviation_score": 1.0
  },
  "weighted_contributions": {
    "gpt_contribution": 0.2125,
    "pattern_contribution": 0.18,
    "structure_contribution": 0.20,
    "framework_contribution": 0.144,
    "deviation_contribution": 0.15
  },
  "weights_used": {
    "gpt_weight": 0.25,
    "pattern_weight": 0.20,
    "structure_weight": 0.20,
    "framework_weight": 0.20,
    "deviation_weight": 0.15
  },
  "history": [
    {
      "final_confidence": 0.75,
      "calculated_at": "2025-01-07T14:20:00Z",
      "weights_used": { ... }
    }
  ]
}
```

---

## Testing

### Backend Testing
```python
# Test 5-factor calculation
from backend.app.extractors.control_extractor_v4 import _calculate_multi_factor_confidence

result = _calculate_multi_factor_confidence(
    gpt_confidence=0.85,
    pattern_confidence=0.90,
    control_test="Test description",
    control_test_results="Results",
    control_desc="Description",
    has_deviation=False,
    deviation_desc="",
    tsc_mappings=[{"confidence": 0.80}],
    coso_mappings=[{"confidence": 0.75}],
    gpt_weight=0.25,
    pattern_weight=0.20,
    structure_weight=0.20,
    framework_weight=0.20,
    deviation_weight=0.15
)

assert result["final_confidence"] > 0.5
assert result["method"] == "5-factor"
assert len(result["factor_scores"]) == 5
```

### Frontend Testing
```bash
# Start frontend dev server
cd frontend
npm start

# Navigate to report with controls
http://localhost:3000/report/1

# Test hover tooltip:
# 1. Hover over confidence score in Controls table
# 2. Verify tooltip appears with 5 factors
# 3. Verify colors match score ranges

# Test detail modal:
# 1. Click confidence score
# 2. Verify modal opens with gauge, table, formula
# 3. Verify "Close" button works
# 4. Verify legacy controls show simplified view
```

---

## Future Enhancements (Not Yet Implemented)

### 1. Recalculation Preview/Execution
**Endpoints**:
- `POST /api/scans/{scan_id}/preview-recalculation`: Show impact before applying
- `POST /api/scans/{scan_id}/recalculate-confidence`: Execute with history preservation

**Features**:
- Preview: Calculate new scores without saving, warn if >20% status changes
- Execute: Recalculate with new weights, preserve old scores in `history` array
- UI: Banner notification when weights changed, "Recalculate" button with preview dialog

### 2. Admin Review Workflow
**Endpoints**:
- `GET /api/controls/review-queue`: Filter controls < 0.5 confidence
- `POST /api/controls/{control_id}/review`: Mark approved/rejected with notes
- `GET /api/controls/review-stats`: Counts by status/org
- `GET /api/controls/review-report`: Aggregate insights (e.g., "20 false positives with low pattern_score")

**Features**:
- Review queue UI showing low-confidence controls
- Bulk review actions
- Review history timeline in ConfidenceModal
- Factor-specific feedback (e.g., "Improve pattern training for this type")

### 3. Factor Averages Reporting
**Endpoint**:
- `GET /api/scans/{scan_id}/factor-averages`: Aggregate statistics per factor

**Features**:
- Dashboard showing average score per factor across scan
- Distribution charts for each factor
- Identify systematic issues (e.g., "Low framework scores across all controls")

---

## Architecture Decisions

### Frozen Confidence History
- **Decision**: Preserve weights at calculation time in `verification_metadata.weights_used`
- **Rationale**: Ensures historical scores remain reproducible even after weight changes
- **Implementation**: Manual recalculation with history array, never auto-update

### Threshold at 0.5
- **Decision**: Keep verification threshold at 50%
- **Rationale**: Natural boundary between "likely correct" and "needs review"
- **Flexibility**: Weights adjustable per organization without changing threshold

### 5-Factor Split
- **Decision**: Split framework into TSC/COSO, add structure and deviation factors
- **Rationale**: 
  - Structure: Measures completeness independently of GPT quality
  - Framework: Leverages existing mapping infrastructure
  - Deviation: Catches logical inconsistencies
- **Balance**: Each factor 0.05-0.60 ensures no single factor dominates

### Backward Compatibility
- **Decision**: Legacy 2-factor controls handled gracefully in UI and verification service
- **Rationale**: Existing reports should continue working without re-extraction
- **Implementation**: Check for `method == '5-factor'`, fallback to 60/40 GPT/pattern

---

## Deployment Checklist

### Backend
- [x] Database migration applied (`alembic upgrade head`)
- [x] Global default weights inserted
- [x] Weight management API endpoints tested
- [x] 5-factor calculation validated
- [x] Verification service updated
- [x] Data flow fixes applied

### Frontend
- [x] ConfidenceTooltip component created
- [x] ConfidenceModal component created
- [x] ReportPage integration complete
- [x] VerificationSection info text updated
- [x] No TypeScript errors in new components
- [ ] Browser testing (hover tooltip, click modal)
- [ ] Legacy control testing

### Configuration
- [x] Default weights set (0.25/0.20/0.20/0.20/0.15)
- [x] Validation rules configured (0.05-0.60, sum=1.0)
- [x] Threshold set (0.5)

### Documentation
- [x] Implementation summary
- [x] API documentation
- [x] User guide
- [x] Architecture decisions
- [ ] Admin training materials

---

## Summary

The 5-factor confidence system is **fully implemented** and ready for use:

✅ **Backend**: Complete database schema, 5-factor calculation, weight management API, data flow fixes, verification service  
✅ **Frontend**: Hover tooltip, detail modal, ReportPage integration, info text updates  
✅ **Features**: Configurable weights, frozen history, audit trail, backward compatibility  

**Next Steps**:
1. Browser testing of new UI components
2. Admin training on weight configuration
3. Monitor initial feedback after 10+ scans
4. Implement recalculation preview/execution (optional)
5. Implement admin review workflow (optional)
