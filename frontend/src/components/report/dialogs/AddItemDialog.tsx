/**
 * AddItemDialog Component
 * 
 * Generic dialog for adding new items (suborgs, CUECs, controls) with auto-fill confidence support.
 * Enhanced with GPT-assisted entity extraction from report context.
 */

import React, { useState, useEffect } from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, TextField, Box, Checkbox, FormControlLabel, Tabs, Tab, Alert, CircularProgress } from '@mui/material';
import axios from 'axios';
import { APP_CONFIG } from '../../../config';

type ResourceType = 'suborg' | 'cuec' | 'control';

interface FieldConfig {
  name: string;
  label: string;
  required?: boolean;
  multiline?: boolean;
  type?: 'text' | 'checkbox';
}

interface AddItemDialogProps {
  open: boolean;
  type: ResourceType;
  scanId: string | null | undefined;
  onClose: () => void;
  onCreate: (data: Record<string, any>) => Promise<void>;
  defaultConfidence: string;
  useDefaultConfidence: boolean;
  onDefaultConfidenceChange: (value: string) => void;
  onUseDefaultConfidenceChange: (checked: boolean) => void;
}

// Field configurations for each resource type
const FIELD_CONFIGS: Record<ResourceType, FieldConfig[]> = {
  suborg: [
    { name: 'name', label: 'Name', required: true },
    { name: 'confidence', label: 'Confidence (e.g., 95% or 0.95)' },
    { name: 'third_party_description', label: 'Description', multiline: true },
    { name: 'third_party_page_ref', label: 'Page Ref' },
  ],
  cuec: [
    { name: 'cuec_description', label: 'Description', required: true, multiline: true },
    { name: 'cuec_confidence', label: 'Confidence (e.g., 95% or 0.95)' },
    { name: 'control_strength', label: 'Control Strength' },
  ],
  control: [
    { name: 'control_id', label: 'Control ID' },
    { name: 'control_desc', label: 'Description', multiline: true },
    { name: 'control_test', label: 'Test Procedures', multiline: true },
    { name: 'control_test_results', label: 'Test Results', multiline: true },
    { name: 'has_deviation', label: 'Has Deviation?', type: 'checkbox' },
    { name: 'deviation_desc', label: 'Deviation Description', multiline: true },
    { name: 'control_confidence', label: 'Confidence (e.g., 95% or 0.95)' },
    { name: 'control_page_ref', label: 'Page Ref' },
  ],
};

// Dialog titles
const DIALOG_TITLES: Record<ResourceType, string> = {
  suborg: 'Add Subservice Organization',
  cuec: 'Add CUEC',
  control: 'Add Control',
};

// Confidence field names for each type
const CONFIDENCE_FIELDS: Record<ResourceType, string> = {
  suborg: 'confidence',
  cuec: 'cuec_confidence',
  control: 'control_confidence',
};

export const AddItemDialog = React.memo(function AddItemDialog({
  open,
  type,
  scanId,
  onClose,
  onCreate,
  defaultConfidence,
  useDefaultConfidence,
  onDefaultConfidenceChange,
  onUseDefaultConfidenceChange,
}: AddItemDialogProps) {
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [activeTab, setActiveTab] = useState(0);
  const [searchText, setSearchText] = useState('');
  const [forceMultiExtract, setForceMultiExtract] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extractionAlert, setExtractionAlert] = useState<{ type: 'success' | 'warning' | 'error'; message: string } | null>(null);
  
  // Framework preview state (tab 2)
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewCacheTime, setPreviewCacheTime] = useState<number | null>(null);

  // Reset form when dialog opens/closes or type changes
  useEffect(() => {
    if (open) {
      setFormData({});
      setActiveTab(0);
      setSearchText('');
      setForceMultiExtract(false);
      setExtracting(false);
      setExtractionAlert(null);
    }
  }, [open, type]);

  // Auto-fill confidence when dialog opens and checkbox is enabled
  useEffect(() => {
    if (open && useDefaultConfidence) {
      const confidenceField = CONFIDENCE_FIELDS[type];
      setFormData(prev => ({ ...prev, [confidenceField]: defaultConfidence }));
    }
  }, [open, useDefaultConfidence, defaultConfidence, type]);

  const handleFieldChange = (fieldName: string, value: any) => {
    setFormData(prev => ({ ...prev, [fieldName]: value }));
  };

  const handleCreate = async () => {
    await onCreate(formData);
  };

  const handlePreviewFrameworks = async () => {
    // Only available for controls and CUECs
    if (type !== 'control' && type !== 'cuec') return;
    
    // Check cache validity (30 seconds)
    const now = Date.now();
    if (previewData && previewCacheTime && (now - previewCacheTime < 30000)) {
      return; // Use cached data
    }
    
    setPreviewLoading(true);
    setPreviewError(null);
    
    try {
      const description = type === 'control' 
        ? formData.control_desc 
        : formData.cuec_description;
      
      if (!description) {
        setPreviewError('Please enter a description first');
        setPreviewLoading(false);
        return;
      }
      
      const requestData: any = {
        control_desc: description,
      };
      
      if (type === 'control' && formData.control_id) {
        requestData.control_id = formData.control_id;
      }
      if (formData.has_deviation) {
        requestData.has_deviation = true;
      }
      
      const response = await axios.post(APP_CONFIG.apiUrl(`/report/${scanId}/preview-frameworks`), requestData);
      setPreviewData(response.data);
      setPreviewCacheTime(now);
    } catch (error: any) {
      console.error('Preview error:', error);
      const message = error?.response?.data?.error || error?.message || 'Failed to preview frameworks';
      setPreviewError(message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleExtractFromReport = async () => {
    if (!searchText.trim()) {
      setExtractionAlert({ type: 'error', message: 'Search term is required' });
      return;
    }

    if (!scanId) {
      setExtractionAlert({ type: 'error', message: 'No scan selected' });
      return;
    }

    setExtracting(true);
    setExtractionAlert(null);

    try {
      const entityTypeMap: Record<ResourceType, string> = {
        suborg: 'subservice_org',
        cuec: 'cuec',
        control: 'control',
      };

      // Use 130-second timeout for GPT extraction (backend has 120s timeout + margin)
      const response = await axios.post(APP_CONFIG.apiUrl(`/report/${scanId}/extract-entity`), {
        entity_type: entityTypeMap[type],
        search_text: searchText,
        force_multi_extract: forceMultiExtract,
      }, { timeout: 130000 });

      const data = response.data;

      // Handle warnings (too many occurrences)
      if (data.warning || data.requires_force) {
        setExtractionAlert({
          type: 'warning',
          message: data.warning || `Found ${data.occurrence_count} occurrences. Consider refining your search or enable 'Force extraction'.`,
        });
        setExtracting(false);
        return;
      }

      // Handle errors
      if (data.error) {
        setExtractionAlert({ type: 'error', message: data.error });
        setExtracting(false);
        return;
      }

      // Success - populate form fields
      const extracted = data.extracted_data;
      const newFormData: Record<string, any> = {};

      // Map extracted fields based on entity type
      if (type === 'control') {
        if (extracted.control_id) newFormData.control_id = extracted.control_id;
        if (extracted.description) newFormData.control_desc = extracted.description;
        // Handle test_procedures as either string or array
        if (extracted.test_procedures) {
          newFormData.control_test = Array.isArray(extracted.test_procedures) 
            ? extracted.test_procedures.join('\n') 
            : extracted.test_procedures;
        }
        // Handle test_results as either string or array
        if (extracted.test_results) {
          newFormData.control_test_results = Array.isArray(extracted.test_results)
            ? extracted.test_results.join('\n')
            : extracted.test_results;
        }
        if (extracted.deviation_description) {
          newFormData.has_deviation = true;
          newFormData.deviation_desc = extracted.deviation_description;
        }
        if (extracted.page_ref) newFormData.control_page_ref = extracted.page_ref;
        if (extracted.confidence) newFormData.control_confidence = Math.round(extracted.confidence * 100) + '%';
      } else if (type === 'cuec') {
        if (extracted.description) newFormData.cuec_description = extracted.description;
        if (extracted.justification) newFormData.cuec_justification = extracted.justification;
        if (extracted.confidence) newFormData.cuec_confidence = Math.round(extracted.confidence * 100) + '%';
      } else if (type === 'suborg') {
        if (extracted.name) newFormData.name = extracted.name;
        if (extracted.description) newFormData.third_party_description = extracted.description;
        if (extracted.page_ref) newFormData.third_party_page_ref = extracted.page_ref;
        if (extracted.confidence) newFormData.confidence = Math.round(extracted.confidence * 100) + '%';
      }

      setFormData(newFormData);
      setExtractionAlert({
        type: 'success',
        message: `Successfully extracted from ${data.occurrence_count} occurrence(s). Review and edit as needed.`,
      });
      
      // Switch to Manual Entry tab to show populated form
      setActiveTab(0);
    } catch (error: any) {
      console.error('Extraction error:', error);
      const message = error?.response?.data?.detail || error?.message || 'Failed to extract entity';
      setExtractionAlert({ type: 'error', message });
    } finally {
      setExtracting(false);
    }
  };

  const fields = FIELD_CONFIGS[type];
  const title = DIALOG_TITLES[type];

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent sx={{ minWidth: type === 'suborg' ? 420 : 520 }}>
        {/* Tabs for Manual Entry vs Search & Extract vs Preview Mappings */}
        <Tabs value={activeTab} onChange={(_, newValue) => setActiveTab(newValue)} sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
          <Tab label="Manual Entry" />
          <Tab label="Search & Extract" />
          {(type === 'control' || type === 'cuec') && <Tab label="Preview Mappings" />}
        </Tabs>

        {/* Tab 0: Manual Entry (existing form) */}
        {activeTab === 0 && (
          <Box>
            {/* Auto-fill confidence controls */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={useDefaultConfidence}
                    onChange={e => onUseDefaultConfidenceChange(e.target.checked)}
                  />
                }
                label={<span style={{ fontSize: 12 }}>Auto-fill confidence</span>}
              />
              <TextField
                size="small"
                label="Default (%)"
                sx={{ width: 120 }}
                value={defaultConfidence}
                onChange={e => onDefaultConfidenceChange(e.target.value)}
              />
            </Box>

            {/* Dynamic fields based on type */}
            {fields.map(field => {
              if (field.type === 'checkbox') {
                return (
                  <Box key={field.name} sx={{ mt: 1, display: 'flex', alignItems: 'center' }}>
                    <input
                      type="checkbox"
                      id={field.name}
                      checked={!!formData[field.name]}
                      onChange={e => handleFieldChange(field.name, e.target.checked)}
                      style={{ marginRight: 8 }}
                    />
                    <label htmlFor={field.name}>{field.label}</label>
                  </Box>
                );
              }
              return (
                <TextField
                  key={field.name}
                  label={field.label}
                  fullWidth
                  multiline={field.multiline}
                  rows={field.multiline ? 3 : 1}
                  sx={{ mt: 1 }}
                  value={formData[field.name] ?? ''}
                  onChange={e => handleFieldChange(field.name, e.target.value)}
                />
              );
            })}
          </Box>
        )}

        {/* Tab 1: Search & Extract */}
        {activeTab === 1 && (
          <Box>
            <TextField
              label="Search Term"
              fullWidth
              placeholder="Enter text to search in the report..."
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              onKeyPress={e => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleExtractFromReport();
                }
              }}
              sx={{ mb: 2 }}
              required
            />

            <FormControlLabel
              control={
                <Checkbox
                  checked={forceMultiExtract}
                  onChange={e => setForceMultiExtract(e.target.checked)}
                />
              }
              label="Force extraction with many matches"
              sx={{ mb: 2 }}
            />

            <Button
              variant="contained"
              onClick={handleExtractFromReport}
              disabled={!searchText.trim() || extracting}
              fullWidth
              sx={{ mb: 2 }}
            >
              {extracting ? <CircularProgress size={24} /> : 'Extract from Report'}
            </Button>

            {/* Alerts */}
            {extractionAlert && (
              <Alert severity={extractionAlert.type} sx={{ mb: 2 }}>
                {extractionAlert.message}
              </Alert>
            )}
          </Box>
        )}

        {/* Tab 2: Preview Mappings (controls and CUECs only) */}
        {activeTab === 2 && (type === 'control' || type === 'cuec') && (
          <Box>
            <Alert severity="info" sx={{ mb: 2 }}>
              ✅ TSC/COSO mappings are computed automatically when you save. Use this preview to verify mappings before creating.
            </Alert>

            <Button
              variant="contained"
              onClick={handlePreviewFrameworks}
              disabled={previewLoading || !formData[type === 'control' ? 'control_desc' : 'cuec_description']}
              fullWidth
              sx={{ mb: 2 }}
            >
              {previewLoading ? <CircularProgress size={24} /> : 'Compute Preview'}
            </Button>

            {previewError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {previewError}
              </Alert>
            )}

            {previewData && !previewLoading && (
              <Box sx={{ mt: 2 }}>
                <Box sx={{ mb: 2 }}>
                  <Box sx={{ fontWeight: 'bold', mb: 1 }}>TSC Matches:</Box>
                  {previewData.tsc_matches && previewData.tsc_matches.length > 0 ? (
                    previewData.tsc_matches.map((match: any, idx: number) => (
                      <Box key={idx} sx={{ ml: 2, mb: 0.5 }}>
                        • <strong>{match.tsc_id}</strong> ({match.score}%)
                        {match.rationale && <Box component="span" sx={{ color: 'text.secondary', fontSize: '0.9em' }}> - {match.rationale}</Box>}
                      </Box>
                    ))
                  ) : (
                    <Box sx={{ ml: 2, color: 'text.secondary' }}>No TSC matches found</Box>
                  )}
                </Box>

                <Box sx={{ mb: 2 }}>
                  <Box sx={{ fontWeight: 'bold', mb: 1 }}>COSO Matches:</Box>
                  {previewData.coso_matches && previewData.coso_matches.length > 0 ? (
                    previewData.coso_matches.map((match: any, idx: number) => (
                      <Box key={idx} sx={{ ml: 2, mb: 0.5 }}>
                        • <strong>Principle {match.principle}</strong> ({match.score}%)
                        {match.rationale && <Box component="span" sx={{ color: 'text.secondary', fontSize: '0.9em' }}> - {match.rationale}</Box>}
                      </Box>
                    ))
                  ) : (
                    <Box sx={{ ml: 2, color: 'text.secondary' }}>No COSO matches found</Box>
                  )}
                </Box>

                {previewData.rate_limit_remaining !== undefined && (
                  <Alert severity="warning" sx={{ fontSize: '0.85em' }}>
                    Rate limit: {previewData.rate_limit_remaining} previews remaining this minute
                  </Alert>
                )}
              </Box>
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleCreate} disabled={activeTab === 1}>
          Create
        </Button>
      </DialogActions>
    </Dialog>
  );
});
