/**
 * Objective Service
 * 
 * API client for control objective extraction and management endpoints.
 * Provides functions for CRUD operations, workflow management, and statistics.
 */

import api from '../api/client';

// ========================
// Type Definitions
// ========================

export interface ControlObjective {
  id: number;
  scan_id: number;
  objective_id: string | null;  // DEPRECATED: Use objective_id_normalized for display/sorting
  objective_id_normalized: string | null;  // Normalized format for consistent display/sorting
  objective_id_original: string | null;  // Original format from PDF for searching
  objective_text: string;
  status: 'pending' | 'approved' | 'rejected';
  extraction_source: string;
  extracted_at: string;
  
  // Confidence metrics
  semantic_coherence?: number;
  keyword_match_score?: number;
  control_alignment_score?: number;
  final_confidence?: number;
  confidence_factors?: any;
  confidence_calc?: string;  // Human-readable calculation string
  confidence_metadata?: {    // Detailed audit trail
    method: string;
    calculated_at: string;
    factor_scores: {
      keyword_confidence: number;
      distance_confidence: number;
      gpt_confidence: number;
      alignment_confidence: number;
      format_confidence: number;
    };
    weighted_contributions: {
      keyword_contribution: number;
      distance_contribution: number;
      gpt_contribution: number;
      alignment_contribution: number;
      format_contribution: number;
    };
    weights_used: {
      keyword: number;
      distance: number;
      gpt_opinion: number;
      alignment: number;
      format: number;
    };
    adjustments: Array<{
      type: string;
      penalty_multiplier: number;
      reason: string;
      applied_at: string;
    }>;
  };
  
  // Individual confidence factors (persisted)
  keyword_confidence?: number;
  distance_confidence?: number;
  gpt_confidence?: number;
  alignment_confidence?: number;
  format_confidence?: number;
  gpt_reasoning?: string;
  
  // Framework mappings
  tsc_mappings?: any;
  coso_mappings?: any;
  
  // Metadata
  page_refs?: number[];
  extracted_from?: string;
  analyst_notes?: string;
  
  // Audit tracking
  approved_by?: string;
  approved_at?: string;
  rejected_by?: string;
  rejected_at?: string;
  converted_to_control_id?: number;
  
  created_at?: string;
  updated_at?: string;
}

export interface ControlObjectiveMapping {
  id: number;
  control_id: number;
  objective_id: number;
  mapping_confidence: number;
  page_proximity_score?: number;
  line_proximity_score?: number;
  gpt_alignment_score?: number;
  id_alignment_score?: number;
  objective_gpt_confidence_boost?: number;
  mapping_justification?: string;
  mapping_rationale?: string;
  created_at?: string;
}

export interface ObjectiveStatistics {
  total_objectives: number;
  by_status: {
    pending: number;
    approved: number;
    rejected: number;
  };
  by_confidence: {
    high: number;
    medium: number;
    low: number;
  };
  avg_confidence: number;
  total_mappings: number;
  unique_controls_mapped: number;
  objectives_without_controls: number;
}

export interface ExtractObjectivesRequest {
  force?: boolean;
  extraction_source?: string;
}

export interface MapObjectivesRequest {
  force?: boolean;
}

export interface BulkApproveRequest {
  objective_ids: number[];
}

export interface BulkRejectRequest {
  objective_ids: number[];
}

export interface ConvertToControlRequest {
  control_desc: string;
  control_test?: string;
  control_test_results?: string;
  deviation_desc?: string;
  control_page_ref?: number | string;
  control_page_refs?: number[] | string[];
  control_line_ref?: number | string;
  control_id?: string;
}

export interface ObjectiveGapLogEntry {
  timestamp: string;
  objective_id: string;
  status: string;
  message: string;
  extracted_id?: string;
}

export interface ObjectiveGapExtractStatus {
  status: string;
  progress_status?: string;
  total_probed?: number;
  total_found?: number;
  total_extracted?: number;
  started_at?: string;
  ended_at?: string;
  duration_seconds?: number;
  pattern_output?: any;
  log?: ObjectiveGapLogEntry[];
  extracted_ids?: string[];
  error?: string;
  cancel_requested?: boolean;
}

// ========================
// Objective CRUD Operations
// ========================

/**
 * Get all objectives for a scan with optional filtering
 */
export async function getObjectives(
  scanId: number,
  params?: {
    status?: string;
    min_confidence?: number;
    page?: number;
    page_size?: number;
  }
): Promise<ControlObjective[]> {
  const response = await api.get(`/report/${scanId}/objectives`, { params });
  // Backend returns { objectives: [...], total: number }, extract the array
  return response.data.objectives || [];
}

/**
 * Get a single objective by ID
 */
export async function getObjective(scanId: number, objectiveId: number): Promise<ControlObjective> {
  const response = await api.get(`/report/${scanId}/objectives/${objectiveId}`);
  return response.data;
}

/**
 * Create a new objective manually
 */
export async function createObjective(
  scanId: number,
  objective: Partial<ControlObjective>
): Promise<ControlObjective> {
  const response = await api.post(`/report/${scanId}/objectives`, objective);
  return response.data;
}

/**
 * Update an existing objective
 */
export async function updateObjective(
  scanId: number,
  objectiveId: number,
  updates: Partial<ControlObjective>
): Promise<ControlObjective> {
  const response = await api.patch(`/report/${scanId}/objectives/${objectiveId}`, updates);
  return response.data;
}

/**
 * Delete an objective
 */
export async function deleteObjective(scanId: number, objectiveId: number): Promise<void> {
  await api.delete(`/report/${scanId}/objectives/${objectiveId}`);
}

/**
 * Merge duplicate objectives and reassign mappings
 */
export async function mergeDuplicateObjectives(
  scanId: number
): Promise<{ merged: number; deleted: number; status: string }> {
  const response = await api.post(`/report/${scanId}/objectives/merge-duplicates`);
  return response.data;
}

// ========================
// Extraction & Mapping Operations
// ========================

/**
 * Extract objectives from report text
 */
export async function extractObjectives(
  scanId: number,
  request: ExtractObjectivesRequest = {}
): Promise<{ message: string; objectives_count: number }> {
  const response = await api.post(`/report/${scanId}/objectives/extract`, request, { timeout: 600000 });
  return response.data;
}

/**
 * Map objectives to controls
 */
export async function mapObjectivesToControls(
  scanId: number,
  request: MapObjectivesRequest = {}
): Promise<{ message: string; mappings_created: number }> {
  const response = await api.post(`/report/${scanId}/objectives/map`, request, { timeout: 600000 });
  return response.data;
}

/**
 * Get objective extraction status
 */
export async function getObjectiveExtractionStatus(
  scanId: number
): Promise<{
  status: string;
  progress_status?: string;
  processed_chunks?: number;
  total_chunks?: number;
  objectives_found?: number;
  error?: string;
}> {
  const response = await api.get(`/report/${scanId}/objectives/extract/status`);
  return response.data;
}

/**
 * Start objective gap extraction
 */
export async function startObjectiveGapExtract(
  scanId: number
): Promise<{ status: string; message?: string; job_id?: string }> {
  const response = await api.post(`/report/${scanId}/objectives/gap-extract`);
  return response.data;
}

/**
 * Cancel objective gap extraction
 */
export async function cancelObjectiveGapExtract(
  scanId: number
): Promise<{ status: string; message?: string }> {
  const response = await api.post(`/report/${scanId}/objectives/gap-extract/cancel`);
  return response.data;
}

/**
 * Get objective gap extraction status
 */
export async function getObjectiveGapExtractStatus(
  scanId: number
): Promise<ObjectiveGapExtractStatus> {
  const response = await api.get(`/report/${scanId}/objectives/gap-extract/status`);
  return response.data;
}

// ========================
// Workflow Operations
// ========================

/**
 * Approve an objective
 */
export async function approveObjective(
  scanId: number,
  objectiveId: number,
  approvedBy: string
): Promise<ControlObjective> {
  const response = await api.post(`/report/${scanId}/objectives/${objectiveId}/approve`);
  return response.data;
}

/**
 * Reject an objective
 */
export async function rejectObjective(
  scanId: number,
  objectiveId: number,
  rejectedBy: string
): Promise<ControlObjective> {
  const response = await api.post(`/report/${scanId}/objectives/${objectiveId}/reject`);
  return response.data;
}

/**
 * Convert objective to control
 */
export async function convertToControl(
  scanId: number,
  objectiveId: number,
  request?: ConvertToControlRequest
): Promise<{ status: string; control_id: string; control_db_id: number; objective_id: number }> {
  const response = await api.post(
    `/report/${scanId}/objectives/${objectiveId}/convert-to-control`,
    request || {}
  );
  return response.data;
}

/**
 * Bulk approve objectives
 */
export async function bulkApproveObjectives(
  scanId: number,
  request: BulkApproveRequest
): Promise<{ updated: number; objectives: ControlObjective[] }> {
  const response = await api.post(`/report/${scanId}/objectives/bulk-approve`, request);
  return response.data;
}

/**
 * Bulk reject objectives
 */
export async function bulkRejectObjectives(
  scanId: number,
  request: BulkRejectRequest
): Promise<{ updated: number; objectives: ControlObjective[] }> {
  const response = await api.post(`/report/${scanId}/objectives/bulk-reject`, request);
  return response.data;
}

// ========================
// Mapping CRUD Operations
// ========================

/**
 * Get all mappings for a scan
 */
export async function getMappings(
  scanId: number,
  params?: {
    control_id?: number;
    objective_id?: number;
  }
): Promise<ControlObjectiveMapping[]> {
  const response = await api.get(`/report/${scanId}/objective-mappings`, { params });
  return response.data;
}

/**
 * Get controls linked to a specific objective (includes mapping details)
 */
export async function getObjectiveControls(
  scanId: number,
  objectiveId: number
): Promise<{ objective_id: number; objective_text: string; controls: any[]; total: number }> {
  const response = await api.get(`/report/${scanId}/objectives/${objectiveId}/controls`);
  return response.data;
}

/**
 * Get objectives linked to a specific control (includes mapping details)
 */
export async function getControlObjectives(
  scanId: number,
  controlId: number
): Promise<{ control_db_id: number; control_id: string; objectives: any[]; total: number }> {
  const response = await api.get(`/report/${scanId}/controls/${controlId}/objectives`);
  return response.data;
}

/**
 * Get highest-confidence objective mappings for all controls in a scan
 */
export async function getPrimaryObjectiveMappings(
  scanId: number
): Promise<{ mappings: any[]; total: number }> {
  const response = await api.get(`/report/${scanId}/controls/primary-objectives`);
  return response.data;
}

/**
 * Get criteria used for the primary objective mapping for a control
 */
export async function getPrimaryObjectiveCriteria(
  scanId: number,
  controlDbId: number
): Promise<any> {
  const response = await api.get(`/report/${scanId}/controls/${controlDbId}/primary-objective/criteria`);
  return response.data;
}

/**
 * Create a new mapping
 */
export async function createMapping(
  scanId: number,
  mapping: Partial<ControlObjectiveMapping>
): Promise<ControlObjectiveMapping> {
  const objectiveId = mapping.objective_id as number | undefined;
  const controlId = mapping.control_id as number | undefined;
  if (!objectiveId || !controlId) {
    throw new Error('objective_id and control_id are required to create a mapping');
  }
  const response = await api.post(
    `/report/${scanId}/objectives/${objectiveId}/controls/${controlId}`,
    {
      mapping_confidence: mapping.mapping_confidence,
    }
  );
  return {
    ...mapping,
    id: response.data.mapping_id ?? response.data.id,
  } as ControlObjectiveMapping;
}

/**
 * Update an existing mapping
 */
export async function updateMapping(
  scanId: number,
  mappingId: number,
  updates: Partial<ControlObjectiveMapping>
): Promise<ControlObjectiveMapping> {
  const response = await api.patch(`/report/${scanId}/mappings/${mappingId}`, updates);
  return response.data;
}

/**
 * Delete a mapping
 */
export async function deleteMapping(
  scanId: number,
  objectiveId: number,
  controlDbId: number
): Promise<void> {
  await api.delete(`/report/${scanId}/objectives/${objectiveId}/controls/${controlDbId}`);
}

/**
 * Convert a control to a control objective
 */
export async function convertControlToObjective(scanId: number, controlDbId: number): Promise<any> {
  const response = await api.post(`/report/${scanId}/controls/${controlDbId}/convert-to-objective`);
  return response.data;
}

// ========================
// Statistics
// ========================

/**
 * Get objective statistics for a scan
 */
export async function getObjectiveStatistics(scanId: number): Promise<ObjectiveStatistics> {
  const response = await api.get(`/report/${scanId}/objectives/statistics`);
  return response.data;
}

// ========================
// Utility Functions
// ========================

/**
 * Format confidence as percentage
 */
export function formatConfidence(confidence?: number): string {
  if (confidence === undefined || confidence === null) return 'N/A';
  return `${Math.round(confidence * 100)}%`;
}

/**
 * Get confidence color based on value
 */
export function getConfidenceColor(confidence?: number): string {
  if (!confidence) return '#999';
  if (confidence >= 0.8) return '#4caf50'; // High - green
  if (confidence >= 0.6) return '#ff9800'; // Medium - orange
  return '#f44336'; // Low - red
}

/**
 * Get status color
 */
export function getStatusColor(status: string): string {
  switch (status) {
    case 'approved':
      return '#4caf50'; // Green
    case 'rejected':
      return '#f44336'; // Red
    case 'pending':
    default:
      return '#ff9800'; // Orange
  }
}

/**
 * Get status label
 */
export function getStatusLabel(status: string): string {
  switch (status) {
    case 'approved':
      return 'Approved';
    case 'rejected':
      return 'Rejected';
    case 'pending':
    default:
      return 'Pending Review';
  }
}

/**
 * Sort objectives by objective_id (ascending, numeric-aware)
 */
export function sortByObjectiveId(objectives: ControlObjective[]): ControlObjective[] {
  return [...objectives].sort((a, b) => {
    const aVal = (a.objective_id || '').trim();
    const bVal = (b.objective_id || '').trim();
    if (!aVal && !bVal) return 0;
    if (!aVal) return 1;
    if (!bVal) return -1;
    return aVal.localeCompare(bVal, undefined, { numeric: true, sensitivity: 'base' });
  });
}

/**
 * Sort objectives by status (pending -> approved -> rejected)
 */
export function sortByStatus(objectives: ControlObjective[]): ControlObjective[] {
  const order: Record<string, number> = { pending: 0, approved: 1, rejected: 2 };
  return [...objectives].sort((a, b) => {
    const aOrder = order[a.status] ?? 99;
    const bOrder = order[b.status] ?? 99;
    return aOrder - bOrder;
  });
}

/**
 * Filter objectives by confidence level
 */
export function filterByConfidence(
  objectives: ControlObjective[],
  minConfidence?: number
): ControlObjective[] {
  if (!minConfidence) return objectives;
  return objectives.filter(
    (obj) => obj.final_confidence !== undefined && obj.final_confidence >= minConfidence
  );
}

/**
 * Group objectives by status
 */
export function groupByStatus(
  objectives: ControlObjective[]
): Record<string, ControlObjective[]> {
  return objectives.reduce((acc, obj) => {
    const status = obj.status || 'pending';
    if (!acc[status]) acc[status] = [];
    acc[status].push(obj);
    return acc;
  }, {} as Record<string, ControlObjective[]>);
}

/**
 * Sort objectives by confidence (descending)
 */
export function sortByConfidence(objectives: ControlObjective[]): ControlObjective[] {
  return [...objectives].sort((a, b) => {
    const confA = a.final_confidence || 0;
    const confB = b.final_confidence || 0;
    return confB - confA;
  });
}
