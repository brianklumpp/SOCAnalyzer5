# Learning Mechanism System - Implementation Plan

**Status:** Ready for Implementation  
**Created:** December 17, 2025  
**Target Completion:** Q2 2026 (6 months)

## Overview

Build an intelligent learning system combining rule-based pattern recognition with selective ML models for complex tasks. The system captures user feedback through random quality prompts (after 10+ minutes of review), learns universal patterns with optional auto-apply, trains ML models on admin-reviewed balanced data, and suggests improvements requiring admin approval.

## Key Design Decisions

1. **Shadow Tests:** Queue when scan pool exhausted, use separate scan sets (10 scans each), invisible to users
2. **Training Data Balance:** Preferentially show underrepresented class for review (45-55% balance required)
3. **Quality Prompts:** Show once per scan after 10+ minutes; if skipped, mark "declined to rate" permanently
4. **Shadow Test Failures:** Retry once automatically
5. **ML Model Versions:** Keep 5 recent versions, archive after 90 days on disk
6. **User Privacy:** Anonymize user IDs after 90 days, preserve admin approval trail
7. **Pattern Learning:** Universal patterns across all organizations (not org-specific)
8. **Rollback Strategy:** Manual admin decision based on suggestions, requires shadow test verification

---

## Implementation Steps

### Step 1: Feedback Collection Infrastructure with One-Time Quality Rating

**Files to Create:**
- Database models in `backend/app/models.py`
- API router `backend/app/routers/learning_router.py`
- Service `backend/app/services/ml_readiness_tracker.py`
- React component `frontend/src/components/learning/FeedbackButton.tsx`
- React component `frontend/src/components/learning/ScanQualityPrompt.tsx`

**Database Tables to Add:**

```python
class UserFeedback(Base):
    __tablename__ = "user_feedback"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey('scans.id'))
    entity_type = Column(String)  # 'control', 'cuec', 'subservice_org'
    entity_id = Column(Integer)
    action_type = Column(String)  # 'edit', 'ignore', 'accept', 'merge', 'manual_extract'
    original_data = Column(JSON)
    corrected_data = Column(JSON)
    context = Column(JSON)  # Surrounding text, page refs
    user_id = Column(Integer, ForeignKey('users.id'))
    anonymized_user_hash = Column(String, nullable=True)
    anonymized_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ExtractionCorrection(Base):
    __tablename__ = "extraction_correction"
    id = Column(Integer, primary_key=True)
    user_feedback_id = Column(Integer, ForeignKey('user_feedback.id'))
    entity_type = Column(String)
    field_name = Column(String)  # 'control_desc', 'control_id', etc.
    original_value = Column(Text)
    corrected_value = Column(Text)
    correction_reason = Column(String)  # 'false_positive', 'incomplete', etc.
    created_at = Column(DateTime, default=datetime.utcnow)

class ManualExtraction(Base):
    __tablename__ = "manual_extraction"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey('scans.id'))
    entity_type = Column(String)
    entity_id = Column(Integer)
    extraction_source = Column(String)  # 'user_added' or 'ai_extracted'
    missed_by_ai_reason = Column(Text, nullable=True)  # Why AI missed it
    page_numbers = Column(JSON)
    section_context = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class ScanQualityRating(Base):
    __tablename__ = "scan_quality_rating"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey('scans.id'), unique=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    overall_rating = Column(Integer, nullable=True)  # 1-5 or null if declined
    accuracy_rating = Column(Integer, nullable=True)  # 1-5
    completeness_rating = Column(Integer, nullable=True)  # 1-5
    comments = Column(Text, nullable=True)
    time_spent_minutes = Column(Integer)
    shown_at = Column(DateTime)
    responded_at = Column(DateTime, nullable=True)
    declined = Column(Boolean, default=False)
    anonymized_user_hash = Column(String, nullable=True)
    anonymized_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class TrainingDataSample(Base):
    __tablename__ = "training_data_sample"
    id = Column(Integer, primary_key=True)
    sample_type = Column(String)  # 'merge_decision', 'user_feedback', 'control_review'
    data = Column(JSON)  # Full sample data
    label = Column(String)  # 'approved', 'rejected', 'correct', 'false_positive'
    class_balance_group = Column(String)  # For tracking balance
    approved_for_training = Column(Boolean, default=False)
    reviewed_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    priority_for_balance = Column(Integer, default=0)  # Higher = prioritize for review
    created_at = Column(DateTime, default=datetime.utcnow)
```

**Settings to Add:**

```python
# In backend/app/models.py Setting table defaults
quality_prompt_probability = 0.2  # 20% of scans
quality_prompt_min_time_minutes = 10
quality_prompt_enabled = True
training_data_auto_approve = False
training_data_balance_threshold = "0.45-0.55"  # JSON string
```

**API Endpoints to Create:**

```
POST   /learning/feedback
POST   /learning/correction
POST   /learning/rate-scan
POST   /learning/decline-rating/{scan_id}
GET    /learning/should-show-quality-prompt/{scan_id}
POST   /learning/track-time/{scan_id}
GET    /learning/metrics
GET    /learning/missed-patterns
GET    /learning/training-readiness
GET    /learning/training-data/pending
POST   /learning/training-data/approve-batch
GET    /learning/training-data/balance-check
```

**Frontend Components:**

- **FeedbackButton.tsx**: Thumbs up/down, "Report Error" modal with field-level corrections
- **ScanQualityPrompt.tsx**: 5-star rating modal (overall, accuracy, completeness), comments field, appears after 10+ min with 20% probability

**Integration Points:**

- Hook into ReportPage.tsx edit/ignore/merge handlers
- Track time spent with 30-second interval updates
- Auto-create TrainingDataSample entries from user actions
- Mark manual additions with `extraction_source='user_added'`

**Estimated Time:** 2-3 weeks

---

### Step 2: Control Review System with Balanced Training Data

**Files to Create:**
- React component `frontend/src/pages/admin/ControlReviewQueue.tsx`
- Service `backend/app/services/balanced_sampling.py`

**API Endpoints to Create:**

```
POST   /learning/control-review
GET    /learning/control-review/queue
PATCH  /learning/control-review/{id}/decision
```

**Features:**

- Display low-confidence controls (<0.5) for admin review
- Decision buttons: "Correct", "False Positive", "Needs Edit", "Uncertain"
- Show extraction context (±3 sentences, page refs, confidence breakdown)
- Track problematic factors (pattern, structure, framework, GPT)
- Store as TrainingDataSample with class balance tracking
- Prioritize underrepresented class in review queue
- Real-time balance indicator with warnings

**UI Design:**

```
┌─────────────────────────────────────────────┐
│ Control Review Queue                        │
│ Class Balance: 68% correct, 32% FP ⚠️       │
│ Showing false positive samples first        │
├─────────────────────────────────────────────┤
│ Control: "User entities must..."           │
│ Confidence: 0.42                            │
│ Factors: GPT(0.25) Pattern(0.08) ...       │
│                                             │
│ Context: "...surrounding text..."          │
│                                             │
│ [Correct] [False Positive] [Uncertain]     │
└─────────────────────────────────────────────┘
```

**Estimated Time:** 1-2 weeks

---

### Step 3: Universal Pattern Learning with Auto-Apply

**Files to Create:**
- Database model `LearnedPattern` in `backend/app/models.py`
- Enhance `backend/app/services/pattern_library.py`
- React component `frontend/src/pages/admin/PatternLibraryManager.tsx`
- React component `frontend/src/pages/admin/PatternReviewUI.tsx`

**Database Table:**

```python
class LearnedPattern(Base):
    __tablename__ = "learned_pattern"
    id = Column(Integer, primary_key=True)
    pattern_type = Column(String)  # 'control_indicator', 'cuec_indicator', 'section_heading'
    pattern_text = Column(Text)  # Regex or exact phrase
    context_type = Column(String)  # 'heading', 'bullet', 'paragraph'
    confidence_weight = Column(Float)  # Boost/reduce confidence
    true_positive_count = Column(Integer, default=0)
    false_positive_count = Column(Integer, default=0)
    accuracy_rate = Column(Float)  # TP / (TP + FP)
    last_validated = Column(DateTime)
    status = Column(String)  # 'candidate', 'approved', 'rejected', 'auto_applied'
    auto_applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

**API Endpoints:**

```
GET    /learning/patterns/candidates
POST   /learning/patterns/approve
POST   /learning/patterns/auto-apply/toggle
GET    /learning/patterns/accuracy
DELETE /learning/patterns/{id}
```

**Features:**

- Detect patterns from manual extractions
- Calculate accuracy from user feedback
- Suggest regex rules from successful contexts
- Auto-apply toggle (default: off, requires 10 TP with 0 FP)
- Complete PatternReviewQueue system for merge approvals

**Estimated Time:** 2 weeks

---

### Step 4: Confidence Calibration with Queueable Shadow Tests

**Files to Create:**
- Service `backend/app/services/confidence_calibrator.py`
- Service `backend/app/services/shadow_test_coordinator.py`
- Database model `ConfidenceWeightTest` in `backend/app/models.py`
- React component `frontend/src/pages/admin/ConfidenceCalibration.tsx`
- Enhance `backend/app/extractors/control_extractor_v4.py`

**Database Table:**

```python
class ConfidenceWeightTest(Base):
    __tablename__ = "confidence_weight_test"
    id = Column(Integer, primary_key=True)
    test_weights = Column(JSON)  # GPT, Pattern, Structure, Framework, Deviation weights
    shadow_mode = Column(Boolean, default=True)
    scans_tested = Column(JSON)  # Array of 10 unique scan IDs
    metrics = Column(JSON)  # precision, recall, F1, acceptance_rate
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String)  # 'queued', 'running', 'completed', 'failed', 'retry', 'approved', 'rejected'
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    visible_to_users = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

**Shadow Test Coordinator Features:**

- Allocate 10 unique scans not used by other active tests
- Queue tests when scan pool exhausted (<10 available)
- Process queue every 5 minutes (scheduled task)
- Retry failed tests once (retry_count < 1)
- Release scans when test completes
- Maintain scan pool from last 30 days

**Multi-Factor Confidence Integration:**

```python
def calculate_multifactor_confidence(control_data, weights):
    """
    GPT score (25%): From GPT reasoning
    Pattern score (20%): From ControlPatternLibrary
    Structure score (20%): Field completeness
    Framework score (20%): Mapping quality
    Deviation score (15%): Has deviation flag
    """
    gpt_score = control_data['gpt_confidence']
    pattern_score = pattern_library.score_control_id(control_data['control_id'])
    structure_score = calculate_structure_completeness(control_data)
    framework_score = calculate_framework_quality(control_data)
    deviation_score = 1.0 if control_data['has_deviation'] else 0.0
    
    return (gpt_score * weights.gpt_weight +
            pattern_score * weights.pattern_weight +
            structure_score * weights.structure_weight +
            framework_score * weights.framework_weight +
            deviation_score * weights.deviation_weight)
```

**Estimated Time:** 2-3 weeks

---

### Step 5: Prompt Optimization with Queueable Shadow Tests

**Files to Create:**
- Database model `PromptVersion` in `backend/app/models.py`
- Service `backend/app/services/prompt_optimizer.py`
- React component `frontend/src/pages/admin/PromptVersionManager.tsx`

**Database Table:**

```python
class PromptVersion(Base):
    __tablename__ = "prompt_version"
    id = Column(Integer, primary_key=True)
    extractor_name = Column(String)  # 'control', 'cuec', 'subservice_org'
    prompt_text = Column(Text)
    version = Column(String)  # Semantic version e.g., "2.1.0"
    performance_metrics = Column(JSON)  # FP rate, FN rate, avg confidence, edit rate
    status = Column(String)  # 'testing', 'approved', 'active'
    shadow_mode = Column(Boolean, default=True)
    test_scan_ids = Column(JSON)  # Array of 10 unique scan IDs
    approval_status = Column(String)  # 'pending', 'approved', 'rejected'
    approved_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    visible_to_users = Column(Boolean, default=False)
    test_status = Column(String)  # 'queued', 'running', 'completed', 'failed', 'retry'
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

**Features:**

- Analyze missed extractions from manual additions
- Generate prompt suggestions ("Look for 'User Responsibilities' sections")
- Run shadow tests on 10 unique scans (queue if pool exhausted)
- Diff viewer showing red/green changes
- Side-by-side comparison (production vs test results)
- Retry failed tests once

**Estimated Time:** 2-3 weeks

---

### Step 6: ML Model Integration with Balanced Training

**Files to Create:**
- Service `backend/app/ml/training_readiness.py`
- Service `backend/app/services/balanced_sampling.py`
- Service `backend/app/services/ml_rollback_verifier.py`
- Service `backend/app/services/ml_version_manager.py`
- ML models `backend/app/ml/duplicate_classifier.py`
- ML models `backend/app/ml/confidence_predictor.py`
- ML serving `backend/app/ml/model_server.py`
- Database model `MLModelVersion` in `backend/app/models.py`
- React component `frontend/src/pages/admin/TrainingDataReview.tsx`
- React component `frontend/src/pages/admin/MLModels.tsx`

**Database Table:**

```python
class MLModelVersion(Base):
    __tablename__ = "ml_model_version"
    id = Column(Integer, primary_key=True)
    model_type = Column(String)  # 'duplicate_classifier', 'confidence_predictor'
    version = Column(String)
    training_samples_count = Column(Integer)
    class_balance_metrics = Column(JSON)  # positive_percent, negative_percent
    performance_metrics = Column(JSON)  # accuracy, precision, recall, F1
    model_file_path = Column(String)  # Path to .pkl file
    trained_at = Column(DateTime)
    deployed_at = Column(DateTime, nullable=True)
    status = Column(String)  # 'training', 'shadow_testing', 'active', 'archived'
    shadow_test_status = Column(String)  # 'queued', 'running', 'completed', 'failed', 'retry'
    retry_count = Column(Integer, default=0)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

**ML Models:**

1. **Duplicate Classifier** (Priority: High)
   - Model: DistilBERT for semantic similarity
   - Training data: 500+ merge decisions (45-55% balance)
   - Replaces GPT similarity (10x faster, 100x cheaper)
   - Target accuracy: 90%+

2. **Confidence Predictor** (Priority: Medium)
   - Model: Binary classifier (XGBoost or Logistic Regression)
   - Training data: 1000+ user feedback samples (45-55% balance)
   - Features: text patterns, context, GPT score, pattern score
   - Target accuracy: 85%+

**Balanced Sampling Features:**

- Calculate current class distribution
- Assign higher priority to underrepresented class
- Get prioritized review queue (minority class first)
- Warn if balance outside 40-60%
- Critical alert if outside 35-65%

**Rollback Verification:**

- Queue shadow test on 10 unique scans
- Compare metrics: rollback version vs current
- Auto-approve if metrics improve or match within 2%
- Require admin approval if metrics degrade
- Retry failed verifications once

**Version Management:**

- Keep 5 most recent versions per model type
- Archive versions older than 90 days to `/app/ml/models/archive/`
- Store on disk (6-8GB for 5 versions × 2 models)
- List archived models from disk

**Training Readiness Tracking:**

Launch date: Dec 17, 2025
- Day 45/90: Check progress
- Target: 500 approved merge decisions + 1000 approved feedback samples
- Balance requirement: 45-55% split
- Estimated collection time: 3 months

**Estimated Time:** 3-4 weeks

---

### Step 7: Admin Learning Dashboard

**Files to Create:**
- React component `frontend/src/pages/admin/LearningDashboard.tsx`

**Tabs:**

1. **Overview**
   - ML training readiness (Day X/90, progress bars)
   - Data collection stats (feedback, merge decisions, quality ratings)
   - System health indicators
   - Shadow test coordination status
   - Queue status (active tests, queued tests, available scan pool)

2. **Pending Approvals**
   - Control reviews (count)
   - Pattern merges (count)
   - Weight adjustments (shadow test status)
   - Prompt versions (shadow test status)
   - Training data samples (count with balance warning)
   - ML model rollbacks (verification status)

3. **Analytics**
   - Extraction quality charts (precision/recall/F1)
   - Confidence accuracy graph
   - User edit rate trends
   - Pattern coverage heatmap
   - Manual extraction analysis
   - Quality ratings over time
   - Training data class balance trends

4. **Pattern Library**
   - All patterns table with accuracy/frequency
   - Auto-apply toggle status
   - Performance over time chart

5. **Confidence Tuning**
   - Current weights (pie chart)
   - Suggested adjustments
   - Shadow test results
   - Historical changes timeline
   - Acceptance rate by confidence band

6. **Prompt Versions**
   - Active prompts per extractor
   - Shadow tests in progress
   - Queue status
   - Performance comparison tables
   - Missed extraction summaries

7. **ML Models**
   - Training readiness panels
   - Training data review link (prioritized queue)
   - Train/Deploy buttons
   - Model version dropdown (5 recent)
   - Rollback verification interface
   - Auto-archive indicator

8. **Training Data**
   - Pending samples (prioritized by balance)
   - Class balance indicators
   - Approval interface
   - Auto-approve toggle
   - Data quality metrics

**Estimated Time:** 2-3 weeks

---

### Step 8: User ID Anonymization

**Files to Create:**
- Service `backend/app/services/anonymizer.py`
- React component `frontend/src/pages/admin/DataRetention.tsx`

**Features:**

- Hash user_id after 90 days (SHA256 + salt)
- Preserve admin trail (approvals, weight changes)
- Scheduled task (daily at 2am)
- Manual trigger for custom timeframes
- Anonymization report with counts and timeline

**Tables to Update:**
- UserFeedback
- ExtractionCorrection
- ControlReview
- ScanQualityRating

Add columns:
- `anonymized_user_hash` (nullable)
- `anonymized_at` (nullable)

**Estimated Time:** 1 week

---

## Implementation Timeline

| Phase | Steps | Duration | Target Date |
|-------|-------|----------|-------------|
| Phase 1 | Steps 1-2 | 4-5 weeks | End of Jan 2026 |
| Phase 2 | Steps 3-4 | 4-5 weeks | End of Feb 2026 |
| Phase 3 | Steps 5-6 | 5-6 weeks | Mid Apr 2026 |
| Phase 4 | Steps 7-8 | 3-4 weeks | Mid May 2026 |
| Testing & Polish | - | 2-3 weeks | End of May 2026 |

**Total Duration:** ~6 months (Dec 2025 - May 2026)

---

## Technical Architecture

### Shadow Test Coordination

```
┌─────────────────────────────────────────────┐
│ Shadow Test Coordinator                     │
├─────────────────────────────────────────────┤
│ Scan Pool (last 30 days):                  │
│   Available: 87 scans                       │
│   In use by tests: 30 scans                 │
│                                             │
│ Active Tests (using different scans):       │
│   - Confidence weight test #1: 10 scans    │
│   - Prompt version test #2: 10 scans       │
│   - ML rollback verify #3: 10 scans        │
│                                             │
│ Queued Tests (waiting for scans):          │
│   - Confidence weight test #4: needs 10    │
│   - Prompt version test #5: needs 10       │
│                                             │
│ Queue processor: Runs every 5 minutes      │
│ Retry logic: 1 retry on failure            │
└─────────────────────────────────────────────┘
```

### Balanced Training Data Flow

```
User Actions → TrainingDataSample (with label)
                      ↓
         Calculate class distribution
                      ↓
         Assign priority_for_balance
           (higher for minority class)
                      ↓
         Admin review (prioritized queue)
                      ↓
         Approve/Reject with balance check
                      ↓
         Training (only if 45-55% balanced)
```

### ML Model Lifecycle

```
Data Collection (3 months)
    ↓
Training Readiness Check
    ↓
Admin Reviews Training Data
    ↓
Train Model (DistilBERT or XGBoost)
    ↓
Shadow Test (10 scans)
    ↓
Admin Approval
    ↓
Deploy to Production
    ↓
Performance Monitoring
    ↓
Retrain when 100+ new approved samples
```

---

## Database Schema Summary

**New Tables (8):**
1. user_feedback
2. extraction_correction
3. manual_extraction
4. scan_quality_rating
5. training_data_sample
6. learned_pattern
7. confidence_weight_test
8. ml_model_version

**Enhanced Tables (2):**
1. prompt_version (extend PromptVersion model)
2. control_review (complete existing stub)

**New Settings (5):**
- quality_prompt_probability
- quality_prompt_min_time_minutes
- quality_prompt_enabled
- training_data_auto_approve
- training_data_balance_threshold
- pattern_auto_apply_enabled
- pattern_auto_apply_threshold

---

## API Endpoints Summary

**New Routers (1):**
- `backend/app/routers/learning_router.py` (~30 endpoints)

**Endpoint Groups:**
- Feedback collection: 7 endpoints
- Control review: 3 endpoints
- Pattern learning: 5 endpoints
- Confidence tuning: 4 endpoints
- Prompt optimization: 5 endpoints
- ML models: 7 endpoints
- Training data: 4 endpoints

---

## Key Metrics to Track

### Data Collection Metrics
- User feedback samples collected
- Merge decisions recorded
- Control reviews completed
- Quality ratings submitted vs declined
- Manual extractions tracked

### Quality Metrics
- Extraction precision, recall, F1 by entity type
- Confidence accuracy (predicted vs actual)
- User edit rate trends
- Pattern accuracy rates
- Class balance percentages

### System Health Metrics
- Shadow test success rate
- Shadow test queue length
- Available scan pool size
- Shadow test retry counts
- ML model performance (accuracy, latency)

### User Engagement Metrics
- Quality prompt response rate (~20% target)
- Time spent before prompt (target: 10+ min)
- Feedback button usage
- Training data review completion rate

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Insufficient training data | Track readiness daily, show projections |
| Imbalanced training data | Preferential sampling, balance warnings |
| Shadow test scan starvation | Queue tests, process every 5 minutes |
| Shadow test failures | Retry once, log errors for investigation |
| ML model degradation | Shadow test before deployment, rollback option |
| User fatigue with prompts | 20% probability, one attempt per scan |
| Disk space for archived models | Monitor usage, 90-day archival, keep 5 versions |
| Privacy concerns | 90-day anonymization, preserve admin trail |

---

## Success Criteria

### Phase 1 (Data Collection)
- ✅ Feedback collection operational
- ✅ Quality ratings showing (20% of scans after 10+ min)
- ✅ Manual extraction tracking working
- ✅ Training data samples accumulating
- ✅ Class balance monitoring active

### Phase 2 (Pattern Learning)
- ✅ Pattern detection from manual extractions
- ✅ Pattern accuracy calculation
- ✅ Pattern approval workflow functional
- ✅ Auto-apply toggle working (default: off)

### Phase 3 (Confidence & Prompts)
- ✅ Multi-factor confidence integrated
- ✅ Shadow test coordination working
- ✅ Queue system handling scan pool exhaustion
- ✅ Prompt optimization with shadow tests
- ✅ Retry logic functioning (1 retry)

### Phase 4 (ML & Dashboard)
- ✅ Duplicate classifier trained (90%+ accuracy)
- ✅ Confidence predictor trained (85%+ accuracy)
- ✅ Rollback verification working
- ✅ Admin dashboard complete with all tabs
- ✅ Version management and archival functional

### Phase 5 (Production Readiness)
- ✅ 500+ approved merge decisions (45-55% balanced)
- ✅ 1000+ approved feedback samples (45-55% balanced)
- ✅ All shadow tests passing
- ✅ User ID anonymization operational
- ✅ System documentation complete

---

## Future Enhancements (Post-Launch)

1. **Advanced ML Models**
   - Fine-tuned transformer for entity extraction
   - Framework mapping model (replace expensive GPT calls)
   - Anomaly detection for unusual report formats

2. **Learning Insights**
   - Quarterly learning reports for prompt engineering
   - Pattern evolution visualization
   - A/B testing for multiple prompt versions simultaneously

3. **Automation Expansion**
   - Auto-approve training data when balance maintained
   - Auto-deploy shadow tests that exceed performance thresholds
   - Intelligent scan pool management with predictive allocation

4. **User Experience**
   - Gamification for feedback collection (leaderboards)
   - Inline suggestions based on learned patterns
   - Real-time confidence explanations

---

## Notes

- Launch date: December 17, 2025
- 3-month data collection milestone: March 17, 2026
- All shadow tests invisible to end users
- All changes require admin approval before production
- Class balance strictly enforced (45-55% range)
- Model versions archived after 90 days on disk
- User IDs anonymized after 90 days (admin trail preserved)

---

**Last Updated:** December 17, 2025
