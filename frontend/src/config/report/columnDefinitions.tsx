/**
 * Column Definitions for Report Tables
 * 
 * Defines column configurations for CUECs, Controls, and Subservice Organizations tables.
 * Extracted from ReportPage.tsx to enable reuse and reduce file size.
 */

import React from 'react';
import { Box, Button } from '@mui/material';
import UniversalFrameworkMapper from '../../components/UniversalFrameworkMapper';
import ConfidenceTooltip from '../../components/ConfidenceTooltip';
import ControlTooltip from '../../components/ControlTooltip';

// ========================
// CUEC COLUMNS
// ========================

export const cuecColumns = (
  frameworkCriteria?: any,
  onOpenMappingDetails?: (control: any, frameworkType: string) => void
) => [
  { key: "cuec_description", label: "Description", width: 400, editable: true },
  {
    key: "cuec_primary_objective",
    label: "Control Objective",
    width: 260,
    editable: false,
    render: (row: any) => {
      const objectiveText = row.cuec_primary_objective?.objective_text || row.cuec_primary_objective_text;
      const objectiveId = row.cuec_primary_objective?.objective_id;
      if (!objectiveText) return null;
      const scores = row.cuec_primary_objective_scores || {};
      const total = typeof scores.total === 'number' ? scores.total : row.cuec_primary_objective_confidence;
      const color = typeof total === 'number' ? (total >= 0.8 ? '#4caf50' : total >= 0.6 ? '#ff9800' : '#f44336') : '#666';
      return (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <span style={{ fontSize: '0.75em', color: '#666' }}>
            ID: {objectiveId || 'Unlabeled'}
          </span>
          <span>{objectiveText}</span>
          {typeof total === 'number' ? (
            <span style={{ fontSize: '0.75em', color, fontWeight: 600 }}>
              {Math.round(total * 100)}% mapping confidence
            </span>
          ) : null}
          {(scores.page_proximity_score || scores.line_proximity_score || scores.gpt_alignment_score) ? (
            <span style={{ fontSize: '0.72em', color: '#666' }}>
              scores: page {scores.page_proximity_score ?? '—'} · line {scores.line_proximity_score ?? '—'} · gpt {scores.gpt_alignment_score ?? '—'}
            </span>
          ) : null}
        </Box>
      );
    }
  },
  { key: "cuec_gpt_reasoning", label: "GPT Reasoning", width: 350, editable: true },
  { key: "cuec_confidence", label: "Confidence", width: 80 },
  { 
    key: "cuec_confidence_justification", 
    label: "Confidence Justification", 
    width: 300, 
    editable: false, 
    format: (v: any) => Array.isArray(v) ? v.join('\n') : (typeof v === 'string' ? v.replace(/,\s*/g, ',\n') : ''), 
    cellSx: { whiteSpace: 'pre-line' } 
  },
  { key: "control_strength", label: "Control Strength", width: 120, format: (v: any) => v || "Not Set", editable: false },
  { 
    key: "framework_mappings", 
    label: "Framework Mappings", 
    width: 250, 
    editable: false, 
    headerInfo: "Click framework chips to view detailed mappings. Use Recompute to refresh.", 
    render: (row: any) => frameworkCriteria && onOpenMappingDetails ? (
      <UniversalFrameworkMapper 
        control={row}
        frameworkCriteria={frameworkCriteria}
        onOpenMappingDetails={onOpenMappingDetails}
      />
    ) : null
  },
  { key: "analyst_notes", label: "Analyst Notes", width: 300, editable: true, cellSx: { whiteSpace: 'pre-wrap' } },
  { 
    key: "edit_log", 
    label: "Edit Log", 
    width: 250, 
    editable: false, 
    format: (v: any) => v || '', 
    cellSx: { whiteSpace: 'pre-wrap', fontSize: '0.85em', color: '#666' } 
  },
  { 
    key: "cuec_page_refs", 
    label: "Page Refs", 
    width: 100, 
    format: (v: any) => Array.isArray(v) ? v.sort((a: number, b: number) => a - b).join(', ') : (v || '')
  },
  // Hidden columns
  { key: "cuec_seq", label: "Seq", width: 80, hidden: true },
  { key: "cuec_line_ref", label: "Line Ref", width: 80, hidden: true },
  { key: "cuec_gpt_opinion", label: "GPT Opinion", width: 80, hidden: true },
  { key: "cuec_distance_from_cuec_keywords", label: "Dist. from Keywords", width: 80, hidden: true },
  { key: "cuec_justification", label: "Justification", width: 200, hidden: true },
];

export const defaultVisibleCuecColumns = [
  "cuec_description",
  "cuec_primary_objective",
  "cuec_confidence",
  "cuec_confidence_justification",
  "control_strength",
  "framework_mappings",
  "cuec_justification",
  "cuec_page_refs",
  "analyst_notes",
  "edit_log"
];

// ========================
// CONTROL COLUMNS
// ========================

export const controlColumns = (
  onOpenConfidenceModal?: (control: any) => void,
  onOpenControlModal?: (control: any) => void,
  frameworkCriteria?: any,
  onOpenMappingDetails?: (control: any, frameworkType: string) => void,
  onOpenObjectiveCriteria?: (control: any) => void,
  onOpenObjectiveEditor?: (control: any) => void,
  onConvertControlToObjective?: (control: any) => void
) => [
  { 
    key: "control_id", 
    label: "Control ID", 
    width: 80,
    editable: true,
    render: (row: any) => onOpenControlModal ? (
      <ControlTooltip control={row} onClick={() => onOpenControlModal(row)}>
        <span style={{ cursor: 'pointer', textDecoration: 'underline', color: '#1976d2' }}>
          {row.control_id || 'N/A'}
        </span>
      </ControlTooltip>
    ) : (row.control_id || 'N/A')
  },
  { key: "control_desc", label: "Description", width: 400, editable: true },
  { 
    key: "primary_objective", 
    label: "Control Objective", 
    width: 300, 
    editable: false,
    format: (v: any) => v?.objective_text || '',
    render: (row: any) => {
      const objectiveText = row.primary_objective?.objective_text || row.primary_objective_text;
      const objectiveId = row.primary_objective?.objective_id;
      const hasObjective = Boolean(objectiveText);
      const mappingConfidence = row.primary_objective_confidence;
      const objectiveConfidence = row.primary_objective?.final_confidence ?? row.primary_objective_confidence ?? 0;
      const confidence = typeof mappingConfidence === 'number' ? mappingConfidence : objectiveConfidence;
      const confidenceLabel = typeof mappingConfidence === 'number' ? 'mapping' : 'objective';
      const confidenceColor = confidence >= 0.8 ? '#4caf50' : confidence >= 0.6 ? '#ff9800' : '#f44336';
      const scores = row.primary_objective_scores || {};
      return (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <span style={{ fontSize: '0.75em', color: '#666' }}>ID: {objectiveId || 'Unlabeled'}</span>
          <span>{objectiveText || 'Unmapped objective'}</span>
          {(scores.page_proximity_score || scores.gpt_alignment_score || scores.id_alignment_score) ? (
            <span style={{ fontSize: '0.72em', color: '#666' }}>
              scores: page {scores.page_proximity_score ?? '—'} · gpt {scores.gpt_alignment_score ?? '—'} · id {scores.id_alignment_score ?? '—'}
            </span>
          ) : null}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            {hasObjective ? (
              <span style={{ fontSize: '0.75em', color: confidenceColor, fontWeight: 'bold' }}>
                {Math.round(confidence * 100)}% {confidenceLabel} confidence
              </span>
            ) : null}
            {onOpenObjectiveCriteria ? (
              <Button
                size="small"
                variant="text"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenObjectiveCriteria(row);
                }}
                sx={{ minWidth: 'auto', padding: '0 6px', fontSize: '0.7rem' }}
              >
                Why?
              </Button>
            ) : null}
            {onOpenObjectiveEditor ? (
              <Button
                size="small"
                variant="text"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenObjectiveEditor(row);
                }}
                sx={{ minWidth: 'auto', padding: '0 6px', fontSize: '0.7rem' }}
              >
                Edit
              </Button>
            ) : null}
          </Box>
        </Box>
      );
    }
  },
  { key: "control_test", label: "Test", width: 320, editable: true },
  { key: "control_test_results", label: "Test Results", width: 160, editable: true },
  { key: "has_deviation", label: "Deviation?", width: 90, format: (v: any) => v ? 'Yes' : '', editable: true },
  { key: "deviation_desc", label: "Deviation Summary", width: 240, editable: true },
  { key: "analyst_notes", label: "Analyst Notes", width: 300, cellSx: { whiteSpace: 'pre-wrap' } },
  { 
    key: "control_confidence", 
    label: "Confidence", 
    width: 100,
    render: (row: any) => (
      <ConfidenceTooltip 
        control={row} 
        onClick={() => onOpenConfidenceModal?.(row)}
      >
        <span style={{ cursor: 'pointer' }}>
          {row.control_confidence}
        </span>
      </ConfidenceTooltip>
    )
  },
  { key: "confidence_calc", label: "Confidence Calculation", width: 300, editable: false, cellSx: { whiteSpace: 'pre-wrap', fontSize: '0.85rem' } },
  { 
    key: "framework_mappings", 
    label: "Framework Mappings", 
    width: 250, 
    editable: false, 
    headerInfo: "Click framework chips to view detailed mappings. Use Recompute to refresh.", 
    render: (row: any) => frameworkCriteria && onOpenMappingDetails ? (
      <UniversalFrameworkMapper 
        control={row}
        frameworkCriteria={frameworkCriteria}
        onOpenMappingDetails={onOpenMappingDetails}
      />
    ) : null
  },
  { key: "control_seq", label: "Seq", width: 80 },
  { 
    key: "control_page_refs", 
    label: "Page Refs", 
    width: 100, 
    format: (v: any) => Array.isArray(v) ? v.sort((a: number, b: number) => a - b).join(', ') : (v || '')
  },
  // Hidden columns
  { key: "control_line_ref", label: "Line Ref", width: 80, hidden: true },
  { key: "merged_to_control_id", label: "Merged To", width: 80, hidden: true },
  { key: "control_gpt_opinion", label: "GPT Opinion", width: 80, hidden: true },
  { key: "control_gpt_reasoning", label: "GPT Reasoning", width: 350, editable: false, hidden: true },
  { 
    key: "confidence_justification", 
    label: "Confidence Justification", 
    width: 300, 
    hidden: true, 
    editable: false, 
    format: (v: any) => {
      if (!v) return '';
      if (Array.isArray(v)) return v.join('\n');
      if (typeof v === 'string') return v;
      return String(v);
    },
    cellSx: { whiteSpace: 'pre-line' } 
  },
  { 
    key: "edit_log", 
    label: "Edit Log", 
    width: 250, 
    editable: false, 
    format: (v: any) => v || '', 
    cellSx: { whiteSpace: 'pre-wrap', fontSize: '0.85em', color: '#666' } 
  },
];

export const defaultVisibleControlColumns = [
  "control_id",
  "control_desc",
  "primary_objective",
  "control_test",
  "control_test_results",
  "has_deviation",
  "control_confidence",
  "framework_mappings",
  "confidence_calc",
  "analyst_notes",
  "edit_log"
];

// Debug: verify default visible columns
console.log('[Column Definitions] Default visible control columns:', defaultVisibleControlColumns);

// ========================
// SUBSERVICE ORGANIZATION COLUMNS
// ========================

export const subserviceOrgColumns = [
  { 
    key: "name", 
    label: "Subservice Organization", 
    width: 220,
    editable: true
  },
  { 
    key: "confidence", 
    label: "Confidence", 
    width: 90, 
    format: (v: any) => {
      if (v === undefined || v === null) return "";
      const num = Number(v);
      return !isNaN(num) && isFinite(num) ? `${Math.round(num * 100)}%` : "0%";
    }
  },
  { key: "third_party_description", label: "Description", width: 220, editable: true },
  { key: "third_party_page_ref", label: "Page Ref", width: 160, editable: true },
  { key: "analyst_notes", label: "Analyst Notes", width: 300, editable: true, cellSx: { whiteSpace: 'pre-wrap' } },
  { 
    key: "edit_log", 
    label: "Edit Log", 
    width: 250, 
    editable: false, 
    format: (v: any) => v || '', 
    cellSx: { whiteSpace: 'pre-wrap', fontSize: '0.85em', color: '#666' } 
  },
  { 
    key: "third_party_confidence", 
    label: "Confidence %", 
    width: 80, 
    hidden: true, 
    format: (v: any) => {
      if (v === undefined || v === null) return "";
      const num = Number(v);
      return !isNaN(num) && isFinite(num) ? `${Math.round(num * 100)}%` : "0%";
    }
  },
  { key: "distance_from_so_keywords", label: "SO Distance", width: 80, hidden: true },
  { key: "likely_so", label: "Likely SO", width: 80, hidden: true },
  { key: "common_so", label: "Common SO", width: 80, hidden: true },
  { key: "source_context", label: "Source Context", width: 120, hidden: true },
  { 
    key: "confidence_justification", 
    label: "Confidence Justification", 
    width: 300, 
    editable: false, 
    format: (v: any) => Array.isArray(v) ? v.join('\n') : (typeof v === 'string' ? v.replace(/,\s*/g, ',\n') : ''), 
    cellSx: { whiteSpace: 'pre-line' } 
  },
];

export const defaultVisibleSubOrgColumns = [
  "name",
  "third_party_description",
  "confidence",
  "confidence_justification",
  "third_party_page_ref",
  "analyst_notes",
  "edit_log"
];
