/**
 * ObjectiveSelector Component
 * 
 * UI component for selecting and linking objectives to controls.
 * Can be used in AddItemDialog or standalone control edit forms.
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Chip,
  Autocomplete,
  TextField,
  Card,
  CardContent,
  IconButton,
  Tooltip,
  CircularProgress,
  Alert,
  createFilterOptions,
} from '@mui/material';
import {
  Delete as DeleteIcon,
} from '@mui/icons-material';
import {
  getObjectives,
  getControlObjectives,
  createMapping,
  deleteMapping,
  formatConfidence,
  getConfidenceColor,
  type ControlObjective,
} from '../services/objectiveService';

interface ObjectiveMapping {
  id?: number;
  objective_id: number;
  objective: ControlObjective;
  mapping_confidence: number;
}

interface ObjectiveSelectorProps {
  scanId: number;
  controlId?: number; // Database ID of the control (if editing existing control)
  initialMappings?: ObjectiveMapping[];
  onChange?: (mappings: ObjectiveMapping[]) => void;
  disabled?: boolean;
}

export const ObjectiveSelector: React.FC<ObjectiveSelectorProps> = ({
  scanId,
  controlId,
  initialMappings = [],
  onChange,
  disabled = false,
}) => {
  const [objectives, setObjectives] = useState<ControlObjective[]>([]);
  const [selectedMappings, setSelectedMappings] = useState<ObjectiveMapping[]>(initialMappings);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const sortedObjectives = React.useMemo(() => {
    const copy = [...objectives];
    const getPageRef = (obj: ControlObjective) => {
      const refs = obj.page_refs as any;
      if (Array.isArray(refs) && refs.length > 0) {
        const nums = refs.map((r) => Number(r)).filter((n) => !Number.isNaN(n));
        return nums.length > 0 ? Math.min(...nums) : Number.MAX_SAFE_INTEGER;
      }
      const single = Number(refs);
      return Number.isNaN(single) ? Number.MAX_SAFE_INTEGER : single;
    };
    copy.sort((a, b) => {
      const aId = (a.objective_id || '').trim();
      const bId = (b.objective_id || '').trim();
      const aHas = Boolean(aId);
      const bHas = Boolean(bId);
      if (aHas && bHas) return aId.localeCompare(bId, undefined, { numeric: true, sensitivity: 'base' });
      if (aHas !== bHas) return aHas ? -1 : 1;
      return getPageRef(a) - getPageRef(b);
    });
    return copy;
  }, [objectives]);

  // Load available objectives
  useEffect(() => {
    const loadObjectives = async () => {
      setLoading(true);
      setError(null);
      
      try {
        // Fetch all objectives for linking
        const data = await getObjectives(scanId);
        setObjectives(data);
      } catch (err: any) {
        console.error('Failed to load objectives:', err);
        setError('Failed to load objectives');
      } finally {
        setLoading(false);
      }
    };
    
    loadObjectives();
  }, [scanId]);

  // Load existing mappings for control
  useEffect(() => {
    if (controlId && initialMappings.length === 0) {
      const loadMappings = async () => {
        try {
          const result = await getControlObjectives(scanId, controlId);
          const mapped = (result.objectives || []).map((entry: any) => ({
            id: entry.mapping_id,
            objective_id: entry.objective?.id,
            objective: entry.objective,
            mapping_confidence: entry.mapping_confidence ?? 1.0,
          })) as ObjectiveMapping[];
          setSelectedMappings(mapped);
        } catch (err: any) {
          console.debug('Failed to load control objectives:', err);
        }
      };

      loadMappings();
    }
  }, [controlId, initialMappings]);

  const handleAddObjective = async (objective: ControlObjective | null) => {
    if (!objective) return;
    
    // Check if already mapped
    if (selectedMappings.some((m) => m.objective_id === objective.id)) {
      return;
    }
    
    const newMapping: ObjectiveMapping = {
      objective_id: objective.id,
      objective,
      mapping_confidence: 1.0, // Default confidence
    };
    
    // If control exists, save to backend
    if (controlId) {
      setSaving(true);
      try {
        const result = await createMapping(scanId, {
          control_id: controlId,
          objective_id: objective.id,
          mapping_confidence: newMapping.mapping_confidence,
        });
        newMapping.id = result.id ?? (result as any).mapping_id;
      } catch (err: any) {
        console.error('Failed to create mapping:', err);
        setError('Failed to link objective');
        setSaving(false);
        return;
      }
      setSaving(false);
    }
    
    const updatedMappings = [...selectedMappings, newMapping];
    setSelectedMappings(updatedMappings);
    onChange?.(updatedMappings);
  };

  const handleRemoveObjective = async (mapping: ObjectiveMapping) => {
    // If control exists and mapping has ID, delete from backend
    if (controlId && mapping.id) {
      setSaving(true);
      try {
        await deleteMapping(scanId, mapping.objective_id, controlId);
      } catch (err: any) {
        console.error('Failed to delete mapping:', err);
        setError('Failed to unlink objective');
        setSaving(false);
        return;
      }
      setSaving(false);
    }
    
    const updatedMappings = selectedMappings.filter((m) => m.objective_id !== mapping.objective_id);
    setSelectedMappings(updatedMappings);
    onChange?.(updatedMappings);
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  if (objectives.length === 0) {
    return (
      <Alert severity="info" sx={{ mt: 1 }}>
        No objectives available. Extract objectives first to link them to controls.
      </Alert>
    );
  }

  const filterOptions = createFilterOptions<ControlObjective>({
    stringify: (option) => {
      const refs = Array.isArray(option.page_refs) ? option.page_refs.join(',') : (option.page_refs ?? '');
      return `${option.objective_id || ''} ${option.objective_text || ''} ${refs}`.toLowerCase();
    }
  });

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        Linked Objectives
      </Typography>
      
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      
      {/* Objective Selection Autocomplete */}
      <Autocomplete
        options={sortedObjectives}
        getOptionLabel={(option) => `${option.objective_id || 'Unlabeled'}: ${option.objective_text}`}
        filterOptions={filterOptions}
        renderInput={(params) => (
          <TextField
            {...params}
            placeholder="Search and select objectives..."
            variant="outlined"
            size="small"
          />
        )}
        renderOption={(props, option) => {
          const refs = Array.isArray(option.page_refs) ? option.page_refs.join(', ') : (option.page_refs ?? '—');
          return (
            <li {...props} key={option.id}>
              <Box sx={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="body2" fontWeight="bold">
                    {option.objective_id || 'Unlabeled'}
                  </Typography>
                  <Chip
                    label={formatConfidence(option.final_confidence)}
                    size="small"
                    sx={{
                      bgcolor: getConfidenceColor(option.final_confidence),
                      color: 'white',
                      height: 18,
                      fontSize: '0.65rem',
                    }}
                  />
                  <Typography variant="caption" color="text.secondary">
                    Page refs: {refs}
                  </Typography>
                </Box>
                <Typography variant="body2" color="textSecondary" noWrap>
                  {option.objective_text}
                </Typography>
              </Box>
            </li>
          );
        }}
        onChange={(_, value) => handleAddObjective(value)}
        disabled={disabled || saving}
        sx={{ mb: 2 }}
      />
      
      {/* Selected Objectives List */}
      {selectedMappings.length > 0 ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {selectedMappings.map((mapping) => (
            <Card key={mapping.objective_id} variant="outlined">
              <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                  <Box sx={{ flex: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      <Typography variant="body2" fontWeight="bold">
                        {mapping.objective.objective_id_normalized || mapping.objective.objective_id}
                      </Typography>
                      <Chip
                        label={formatConfidence(mapping.objective.final_confidence)}
                        size="small"
                        sx={{
                          bgcolor: getConfidenceColor(mapping.objective.final_confidence),
                          color: 'white',
                          height: 18,
                          fontSize: '0.65rem',
                        }}
                      />

                    </Box>
                    <Typography variant="body2" color="textSecondary">
                      {mapping.objective.objective_text}
                    </Typography>
                    {mapping.mapping_justification && (
                      <Typography 
                        variant="caption" 
                        sx={{ 
                          display: 'block', 
                          mt: 0.5, 
                          fontSize: '0.75em', 
                          color: 'text.secondary',
                          whiteSpace: 'pre-line',
                          fontFamily: 'monospace'
                        }}
                      >
                        {mapping.mapping_justification}
                      </Typography>
                    )}
                  </Box>
                  
                  <Box sx={{ display: 'flex', gap: 0.5 }}>
                    <Tooltip title="Remove objective">
                      <IconButton
                        size="small"
                        onClick={() => handleRemoveObjective(mapping)}
                        disabled={disabled || saving}
                        color="error"
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          ))}
        </Box>
      ) : (
        <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', p: 2, textAlign: 'center' }}>
          No objectives linked. Select from the dropdown above to link objectives to this control.
        </Typography>
      )}
    </Box>
  );
};

export default ObjectiveSelector;
