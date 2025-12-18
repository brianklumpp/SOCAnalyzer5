import React, { useState, useEffect, useMemo } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  LinearProgress,
  Chip,
  IconButton,
  TextField,
  Divider,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel
} from '@mui/material';
import {
  Close as CloseIcon,
  Edit as EditIcon,
  Save as SaveIcon,
  Cancel as CancelIcon,
  Delete as DeleteIcon,
  Add as AddIcon,
  Warning as WarningIcon
} from '@mui/icons-material';
import api from '../api/client';

interface FrameworkMatch {
  id: string;
  confidence: number;
  reasoning?: string;
  aspect_addressed?: string;
  keywords_matched?: string[];
  deviation?: string | null;
}

interface FrameworkCriteria {
  framework_name: string;
  display_name: string;
  color: string;
  icon: string;
  sections: { [section: string]: Array<{ id: string; description: string; name?: string }> };
}

interface FrameworkMappingDetailsModalProps {
  open: boolean;
  control: any;
  frameworkType: string;
  frameworkCriteria: { [key: string]: FrameworkCriteria };
  onClose: () => void;
  onUpdate: () => void;
  scanId: number;
}

/**
 * Framework Mapping Details Modal
 * 
 * Displays and allows editing of all framework mappings for a specific framework.
 * Shows full text (no truncation), confidence scores, keywords, and supports inline editing.
 */
export const FrameworkMappingDetailsModal: React.FC<FrameworkMappingDetailsModalProps> = ({
  open,
  control,
  frameworkType,
  frameworkCriteria,
  onClose,
  onUpdate,
  scanId
}) => {
  const [mappings, setMappings] = useState<FrameworkMatch[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editedMapping, setEditedMapping] = useState<FrameworkMatch | null>(null);
  const [saving, setSaving] = useState(false);
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [selectedFrameworkForAdd, setSelectedFrameworkForAdd] = useState<string>('');
  const [newMapping, setNewMapping] = useState<Partial<FrameworkMatch>>({
    id: '',
    confidence: 0.8,
    reasoning: '',
    aspect_addressed: '',
    keywords_matched: [],
    deviation: null
  });

  // Load mappings when modal opens
  useEffect(() => {
    if (open && control && frameworkType) {
      const frameworkMappings = control.framework_mappings?.[frameworkType] || [];
      setMappings(frameworkMappings);
      setEditingIndex(null);
      setEditedMapping(null);
    }
  }, [open, control, frameworkType]);

  // Case-insensitive framework lookup
  const getCriteriaForFramework = (fwType: string) => {
    // Try exact match first
    if (frameworkCriteria[fwType]) return frameworkCriteria[fwType];
    // Try lowercase
    const lowerKey = fwType.toLowerCase();
    if (frameworkCriteria[lowerKey]) return frameworkCriteria[lowerKey];
    // Try uppercase
    const upperKey = fwType.toUpperCase();
    if (frameworkCriteria[upperKey]) return frameworkCriteria[upperKey];
    // Try case-insensitive search
    const key = Object.keys(frameworkCriteria).find(k => k.toLowerCase() === lowerKey);
    return key ? frameworkCriteria[key] : null;
  };

  const criteria = getCriteriaForFramework(frameworkType);
  const displayName = criteria?.display_name || frameworkType;
  const color = criteria?.color || '#1976d2';

  // Get criterion details from criteria data
  const getCriterionDetails = (criterionId: string) => {
    if (!criteria?.sections) {
      console.log('No criteria sections available', { frameworkType, criteria });
      return null;
    }
    
    for (const section of Object.values(criteria.sections)) {
      if (Array.isArray(section)) {
        const criterion = section.find((c: any) => c.id === criterionId);
        if (criterion) {
          console.log('Found criterion details:', criterion);
          return criterion;
        }
      }
    }
    console.log('No criterion found for ID:', criterionId);
    return null;
  };

  // Get all available criteria for dropdown based on selected framework
  const availableCriteria = useMemo(() => {
    const selectedCriteria = selectedFrameworkForAdd 
      ? getCriteriaForFramework(selectedFrameworkForAdd)
      : criteria;
    
    if (!selectedCriteria?.sections) {
      console.log('No sections for selected framework:', selectedFrameworkForAdd || frameworkType);
      return [];
    }
    
    const allCriteria: any[] = [];
    Object.entries(selectedCriteria.sections).forEach(([sectionName, section]) => {
      if (Array.isArray(section)) {
        section.forEach((criterion: any) => {
          allCriteria.push({
            ...criterion,
            sectionName
          });
        });
      }
    });
    console.log('Available criteria for dropdown:', allCriteria.length, 'from framework:', selectedFrameworkForAdd || frameworkType);
    return allCriteria;
  }, [selectedFrameworkForAdd, frameworkType, frameworkCriteria]);

  const handleEdit = (index: number) => {
    setEditingIndex(index);
    setEditedMapping({ ...mappings[index] });
  };

  const handleCancelEdit = () => {
    setEditingIndex(null);
    setEditedMapping(null);
  };

  const handleSaveEdit = async () => {
    if (editingIndex === null || !editedMapping) return;

    const updatedMappings = [...mappings];
    updatedMappings[editingIndex] = editedMapping;

    await saveMappings(updatedMappings);
    setEditingIndex(null);
    setEditedMapping(null);
  };

  const handleRemoveMapping = async (index: number) => {
    const updatedMappings = mappings.filter((_, i) => i !== index);
    await saveMappings(updatedMappings);
  };

  const saveMappings = async (updatedMappings: FrameworkMatch[]) => {
    setSaving(true);
    try {
      const isControl = control.control_id !== undefined || control.control_desc !== undefined;
      const endpoint = isControl
        ? `/report/${scanId}/controls/${control.id}`
        : `/report/${scanId}/cuecs/${control.id}`;

      // Update framework_mappings with new mappings for this framework
      const updatedFrameworkMappings = {
        ...(control.framework_mappings || {}),
        [frameworkType]: updatedMappings
      };

      await api.patch(endpoint, {
        framework_mappings: updatedFrameworkMappings
      });

      setMappings(updatedMappings);
      onUpdate();
    } catch (error) {
      console.error('Failed to save framework mappings:', error);
      alert('Failed to save mappings. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleFieldChange = (field: keyof FrameworkMatch, value: any) => {
    if (!editedMapping) return;
    setEditedMapping({
      ...editedMapping,
      [field]: value
    });
  };

  const handleNewMappingFieldChange = (field: keyof FrameworkMatch, value: any) => {
    setNewMapping({
      ...newMapping,
      [field]: value
    });
  };

  const handleStartAddMapping = () => {
    setIsAddingNew(true);
    setSelectedFrameworkForAdd(frameworkType); // Default to current framework
    setNewMapping({
      id: '',
      confidence: 0.8,
      reasoning: '',
      aspect_addressed: '',
      keywords_matched: [],
      deviation: null
    });
  };

  const handleCancelAddMapping = () => {
    setIsAddingNew(false);
    setSelectedFrameworkForAdd('');
    setNewMapping({
      id: '',
      confidence: 0.8,
      reasoning: '',
      aspect_addressed: '',
      keywords_matched: [],
      deviation: null
    });
  };

  const handleSaveNewMapping = async () => {
    if (!selectedFrameworkForAdd) {
      alert('Please select a framework');
      return;
    }
    if (!newMapping.id) {
      alert('Please select a criterion');
      return;
    }

    const newMappingComplete: FrameworkMatch = {
      id: newMapping.id,
      confidence: newMapping.confidence || 0.8,
      reasoning: newMapping.reasoning || '',
      aspect_addressed: newMapping.aspect_addressed || '',
      keywords_matched: newMapping.keywords_matched || [],
      deviation: newMapping.deviation || null
    };

    // If adding to current framework, update current mappings
    if (selectedFrameworkForAdd.toLowerCase() === frameworkType.toLowerCase()) {
      const updatedMappings = [...mappings, newMappingComplete];
      await saveMappings(updatedMappings);
    } else {
      // Adding to different framework - update that framework's mappings
      const currentFrameworkMappings = control.framework_mappings || {};
      const targetFrameworkMappings = currentFrameworkMappings[selectedFrameworkForAdd] || [];
      const updatedTargetMappings = [...targetFrameworkMappings, newMappingComplete];
      
      const updatedAllFrameworkMappings = {
        ...currentFrameworkMappings,
        [selectedFrameworkForAdd]: updatedTargetMappings
      };
      
      try {
        setSaving(true);
        const endpoint = control.control_id 
          ? `/report/${scanId}/controls/${control.id}`
          : `/report/${scanId}/cuecs/${control.id}`;
        
        await api.patch(endpoint, { framework_mappings: updatedAllFrameworkMappings });
        onUpdate();
        alert(`Mapping added to ${selectedFrameworkForAdd} framework successfully!`);
      } catch (error) {
        console.error('Failed to save mapping:', error);
        alert('Failed to save mapping. Please try again.');
      } finally {
        setSaving(false);
      }
    }
    setIsAddingNew(false);
    setSelectedFrameworkForAdd('');
  };

  if (!open || !control) return null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          backgroundColor: '#f8f9fa',
          backgroundImage: 'none'
        }
      }}
    >
      <DialogTitle sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        borderBottom: `2px solid ${color}`,
        backgroundColor: '#ffffff'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="h6" component="div" sx={{ color: '#1a1a1a' }}>
            {displayName} Mappings
          </Typography>
          <Chip
            label={`${mappings.length} mapping${mappings.length !== 1 ? 's' : ''}`}
            size="small"
            sx={{ 
              backgroundColor: `${color}`,
              color: '#ffffff',
              fontWeight: 500
            }}
          />
        </Box>
        <IconButton onClick={onClose} size="small" sx={{ color: '#424242' }}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ mt: 2, backgroundColor: '#f8f9fa' }}>
        {control.control_id && (
          <Box sx={{ mb: 2, p: 2, backgroundColor: '#e3f2fd', border: '1px solid #2196f3', borderRadius: 1 }}>
            <Typography variant="subtitle2" sx={{ color: '#1976d2', fontWeight: 600, mb: 1 }}>
              Control: {control.control_id}
            </Typography>
            <Typography variant="body2" sx={{ color: '#1a1a1a' }}>
              {control.control_desc || 'No description available'}
            </Typography>
          </Box>
        )}

        {!control.control_id && (control as any).cuec_description && (
          <Box sx={{ mb: 2, p: 2, backgroundColor: '#fff3e0', border: '1px solid #ff9800', borderRadius: 1 }}>
            <Typography variant="subtitle2" sx={{ color: '#e65100', fontWeight: 600, mb: 1 }}>
              CUEC Description
            </Typography>
            <Typography variant="body2" sx={{ color: '#1a1a1a' }}>
              {(control as any).cuec_description || 'No description available'}
            </Typography>
          </Box>
        )}

        {/* Add New Mapping Form */}
        {isAddingNew && (
          <Box sx={{ 
            mb: 2, 
            p: 2, 
            border: '2px solid #4caf50', 
            borderRadius: 2, 
            backgroundColor: '#f1f8e9' 
          }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ color: '#2e7d32', mb: 2 }}>
              Add New Mapping
            </Typography>
            
            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
              <InputLabel>Select Framework</InputLabel>
              <Select
                value={selectedFrameworkForAdd}
                onChange={(e) => {
                  setSelectedFrameworkForAdd(e.target.value);
                  setNewMapping({ ...newMapping, id: '' }); // Reset criterion when framework changes
                }}
                label="Select Framework"
                sx={{ backgroundColor: '#ffffff' }}
              >
                {Object.entries(frameworkCriteria).map(([key, fw]: [string, any]) => (
                  <MenuItem key={key} value={key}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box sx={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: fw.color }} />
                      <Typography variant="body2">{fw.display_name}</Typography>
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            
            <FormControl fullWidth size="small" sx={{ mb: 2 }} disabled={!selectedFrameworkForAdd}>
              <InputLabel>Select Criterion {selectedFrameworkForAdd && `(${getCriteriaForFramework(selectedFrameworkForAdd)?.display_name || selectedFrameworkForAdd})`}</InputLabel>
              <Select
                value={newMapping.id || ''}
                onChange={(e) => handleNewMappingFieldChange('id', e.target.value)}
                label={`Select Criterion ${selectedFrameworkForAdd ? `(${getCriteriaForFramework(selectedFrameworkForAdd)?.display_name || selectedFrameworkForAdd})` : ''}`}
                sx={{ backgroundColor: '#ffffff' }}
              >
                {availableCriteria.map((criterion: any) => (
                  <MenuItem key={criterion.id} value={criterion.id}>
                    <Box>
                      <Typography variant="body2" fontWeight={600}>
                        {criterion.id} ({criterion.sectionName})
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', whiteSpace: 'normal' }}>
                        {criterion.description?.substring(0, 150)}{criterion.description?.length > 150 ? '...' : ''}
                      </Typography>
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              label="Confidence (0.0 - 1.0)"
              type="number"
              value={newMapping.confidence}
              onChange={(e) => handleNewMappingFieldChange('confidence', parseFloat(e.target.value))}
              inputProps={{ min: 0, max: 1, step: 0.01 }}
              size="small"
              fullWidth
              sx={{ mb: 2, backgroundColor: '#ffffff' }}
            />

            <TextField
              label="Reasoning"
              value={newMapping.reasoning || ''}
              onChange={(e) => handleNewMappingFieldChange('reasoning', e.target.value)}
              multiline
              rows={3}
              size="small"
              fullWidth
              placeholder="Explain why this criterion applies to this control"
              sx={{ mb: 2, backgroundColor: '#ffffff' }}
            />

            <TextField
              label="Aspect Addressed"
              value={newMapping.aspect_addressed || ''}
              onChange={(e) => handleNewMappingFieldChange('aspect_addressed', e.target.value)}
              multiline
              rows={2}
              size="small"
              fullWidth
              placeholder="What specific aspect of the criterion does this control address?"
              sx={{ mb: 2, backgroundColor: '#ffffff' }}
            />

            <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
              <Button
                variant="outlined"
                size="small"
                onClick={handleCancelAddMapping}
                sx={{ color: '#757575', borderColor: '#e0e0e0' }}
              >
                Cancel
              </Button>
              <Button
                variant="contained"
                size="small"
                onClick={handleSaveNewMapping}
                startIcon={<SaveIcon />}
                disabled={!newMapping.id || saving}
                sx={{ backgroundColor: '#2e7d32', '&:hover': { backgroundColor: '#1b5e20' } }}
              >
                Save Mapping
              </Button>
            </Box>
          </Box>
        )}

        {mappings.length === 0 && !isAddingNew ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography sx={{ color: '#616161' }}>
              No mappings found for this framework.
            </Typography>
          </Box>
        ) : mappings.length > 0 ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {mappings.map((mapping, index) => {
              const criterionDetails = getCriterionDetails(mapping.id);
              const isEditing = editingIndex === index;
              const currentMapping = isEditing ? editedMapping! : mapping;

              return (
                <Box
                  key={index}
                  sx={{
                    p: 2,
                    border: `2px solid ${color}`,
                    borderRadius: 2,
                    backgroundColor: isEditing ? '#fff9e6' : '#ffffff',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.12)'
                  }}
                >
                  {/* Header - Criterion ID and Confidence */}
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1 }}>
                    <Box sx={{ flex: 1, mr: 2 }}>
                      <Typography variant="subtitle1" fontWeight={600} sx={{ color: '#1a1a1a', mb: 0.5 }}>
                        {mapping.id}
                      </Typography>
                      {criterionDetails?.description && (
                        <Typography variant="body2" sx={{ color: '#616161', mb: 1 }}>
                          {criterionDetails.description}
                        </Typography>
                      )}
                    </Box>
                    
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {!isEditing ? (
                        <>
                          <IconButton size="small" onClick={() => handleEdit(index)} title="Edit" sx={{ color: '#1976d2' }}>
                            <EditIcon fontSize="small" />
                          </IconButton>
                          <IconButton 
                            size="small" 
                            onClick={() => handleRemoveMapping(index)}
                            title="Remove"
                            sx={{ color: '#d32f2f' }}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </>
                      ) : (
                        <>
                          <IconButton size="small" onClick={handleSaveEdit} title="Save" sx={{ color: '#2e7d32' }}>
                            <SaveIcon fontSize="small" />
                          </IconButton>
                          <IconButton size="small" onClick={handleCancelEdit} title="Cancel" sx={{ color: '#757575' }}>
                            <CancelIcon fontSize="small" />
                          </IconButton>
                        </>
                      )}
                    </Box>
                  </Box>

                  {/* Confidence Bar */}
                  <Box sx={{ mb: 2 }}>
                    {isEditing ? (
                      <TextField
                        label="Confidence"
                        type="number"
                        value={currentMapping.confidence}
                        onChange={(e) => handleFieldChange('confidence', parseFloat(e.target.value))}
                        inputProps={{ min: 0, max: 1, step: 0.01 }}
                        size="small"
                        fullWidth
                      />
                    ) : (
                      <>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                          <Typography variant="caption" sx={{ color: '#616161' }}>
                            Confidence
                          </Typography>
                          <Typography variant="caption" fontWeight={600} sx={{ color: '#1a1a1a' }}>
                            {Math.round(currentMapping.confidence * 100)}%
                          </Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={currentMapping.confidence * 100}
                          sx={{
                            height: 8,
                            borderRadius: 1,
                            backgroundColor: '#e0e0e0',
                            '& .MuiLinearProgress-bar': {
                              backgroundColor: color
                            }
                          }}
                        />
                      </>
                    )}
                  </Box>

                  {/* Reasoning */}
                  {isEditing ? (
                    <TextField
                      label="Reasoning"
                      value={currentMapping.reasoning || ''}
                      onChange={(e) => handleFieldChange('reasoning', e.target.value)}
                      multiline
                      rows={3}
                      size="small"
                      fullWidth
                      sx={{ mb: 2 }}
                    />
                  ) : (
                    currentMapping.reasoning && (
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="caption" sx={{ color: '#616161' }} display="block" gutterBottom>
                          Reasoning
                        </Typography>
                        <Typography variant="body2" sx={{ color: '#1a1a1a' }}>
                          {currentMapping.reasoning}
                        </Typography>
                      </Box>
                    )
                  )}

                  {/* Aspect Addressed */}
                  {isEditing ? (
                    <TextField
                      label="Aspect Addressed"
                      value={currentMapping.aspect_addressed || ''}
                      onChange={(e) => handleFieldChange('aspect_addressed', e.target.value)}
                      multiline
                      rows={2}
                      size="small"
                      fullWidth
                      sx={{ mb: 2 }}
                    />
                  ) : (
                    currentMapping.aspect_addressed && (
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="caption" sx={{ color: '#616161' }} display="block" gutterBottom>
                          Aspect Addressed
                        </Typography>
                        <Typography variant="body2" sx={{ color: '#1a1a1a' }}>
                          {currentMapping.aspect_addressed}
                        </Typography>
                      </Box>
                    )
                  )}

                  {/* Keywords Matched */}
                  {currentMapping.keywords_matched && currentMapping.keywords_matched.length > 0 && (
                    <Box sx={{ mb: 1 }}>
                      <Typography variant="caption" sx={{ color: '#616161' }} display="block" gutterBottom>
                        Keywords Matched
                      </Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {currentMapping.keywords_matched.map((keyword, i) => (
                          <Chip
                            key={i}
                            label={keyword}
                            size="small"
                            sx={{ 
                              fontSize: '0.7rem',
                              height: 20,
                              backgroundColor: '#e3f2fd',
                              color: '#1976d2',
                              border: '1px solid #90caf9'
                            }}
                          />
                        ))}
                      </Box>
                    </Box>
                  )}

                  {/* Deviation Warning */}
                  {currentMapping.deviation && (
                    <Alert severity="warning" icon={<WarningIcon />} sx={{ mt: 1 }}>
                      <Typography variant="caption">
                        <strong>Deviation:</strong> {currentMapping.deviation}
                      </Typography>
                    </Alert>
                  )}

                  {/* Full Criterion Description */}
                  {criterionDetails?.description && (
                    <>
                      <Divider sx={{ my: 1.5, borderColor: '#e0e0e0' }} />
                      <Box>
                        <Typography variant="caption" sx={{ color: '#616161' }} display="block" gutterBottom>
                          Full Criterion Description
                        </Typography>
                        <Typography variant="body2" sx={{ color: '#616161', fontStyle: 'italic' }}>
                          {criterionDetails.description}
                        </Typography>
                      </Box>
                    </>
                  )}
                </Box>
              );
            })}
          </Box>
        ) : null}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2, backgroundColor: '#ffffff', borderTop: '1px solid #e0e0e0' }}>
        {!isAddingNew ? (
          <Button
            startIcon={<AddIcon />}
            variant="outlined"
            size="small"
            onClick={handleStartAddMapping}
            sx={{ color: '#1976d2', borderColor: '#1976d2', '&:hover': { backgroundColor: '#e3f2fd' } }}
          >
            Add Mapping
          </Button>
        ) : (
          <Button
            variant="outlined"
            size="small"
            onClick={handleCancelAddMapping}
            sx={{ color: '#757575', borderColor: '#e0e0e0' }}
          >
            Cancel Add
          </Button>
        )}
        <Box sx={{ flex: 1 }} />
        <Button 
          onClick={onClose} 
          disabled={saving}
          variant="contained"
          sx={{ backgroundColor: '#1976d2', '&:hover': { backgroundColor: '#1565c0' } }}
        >
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default FrameworkMappingDetailsModal;
