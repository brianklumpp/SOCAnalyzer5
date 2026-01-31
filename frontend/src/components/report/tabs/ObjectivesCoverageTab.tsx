/**
 * ObjectivesCoverageTab Component
 * 
 * Displays control objectives grouped with their linked controls.
 * Shows mapping confidence, primary designation, and coverage statistics.
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress,
  Alert,
  Button,
  IconButton,
  Tooltip,
  Divider,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  Refresh as RefreshIcon,
  Link as LinkIcon,
} from '@mui/icons-material';
import {
  getObjectives,
  getObjectiveControls,
  formatConfidence,
  getConfidenceColor,
  getStatusColor,
  getStatusLabel,
  type ControlObjective,
} from '../../../services/objectiveService';

interface ObjectivesCoverageTabProps {
  scanId: number;
  onOpenControlModal?: (control: any) => void;
  onRefresh?: () => void;
}

export const ObjectivesCoverageTab: React.FC<ObjectivesCoverageTabProps> = ({
  scanId,
  onOpenControlModal,
  onRefresh,
}) => {
  const [objectives, setObjectives] = useState<ControlObjective[]>([]);
  const [objectiveControls, setObjectiveControls] = useState<Map<number, any[]>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedObjective, setExpandedObjective] = useState<number | false>(false);

  // Load objectives and their controls
  const loadData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      // Fetch all approved objectives
      const objectivesData = await getObjectives(scanId, { status: 'approved' });
      setObjectives(objectivesData);
      
      // Fetch controls for each objective
      const controlsMap = new Map<number, any[]>();
      await Promise.all(
        objectivesData.map(async (obj) => {
          try {
            const result = await getObjectiveControls(scanId, obj.id);
            controlsMap.set(obj.id, result.controls || []);
          } catch (err) {
            console.debug(`No controls for objective ${obj.id}`);
            controlsMap.set(obj.id, []);
          }
        })
      );
      
      setObjectiveControls(controlsMap);
    } catch (err: any) {
      console.error('Failed to load objectives coverage:', err);
      setError(err.message || 'Failed to load objectives');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [scanId]);

  // Calculate coverage statistics
  const stats = useMemo(() => {
    const totalObjectives = objectives.length;
    const objectivesWithControls = Array.from(objectiveControls.values()).filter(
      (controls) => controls.length > 0
    ).length;
    const objectivesWithoutControls = totalObjectives - objectivesWithControls;
    
    const totalMappings = Array.from(objectiveControls.values()).reduce(
      (sum, controls) => sum + controls.length,
      0
    );
    
    const primaryMappings = Array.from(objectiveControls.values()).reduce(
      (sum, controls) => sum + controls.filter((c) => c.is_primary).length,
      0
    );
    
    const avgConfidence =
      objectives.length > 0
        ? objectives.reduce((sum, obj) => sum + (obj.final_confidence || 0), 0) / objectives.length
        : 0;
    
    return {
      totalObjectives,
      objectivesWithControls,
      objectivesWithoutControls,
      totalMappings,
      primaryMappings,
      avgConfidence,
    };
  }, [objectives, objectiveControls]);

  const handleAccordionChange = (objectiveId: number) => (_: any, isExpanded: boolean) => {
    setExpandedObjective(isExpanded ? objectiveId : false);
  };

  const handleControlClick = (control: any) => {
    if (onOpenControlModal) {
      onOpenControlModal(control);
    }
  };

  const handleRefresh = () => {
    loadData();
    onRefresh?.();
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ m: 2 }}>
        {error}
        <Button onClick={handleRefresh} sx={{ ml: 2 }}>
          Retry
        </Button>
      </Alert>
    );
  }

  if (objectives.length === 0) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="info" icon={<InfoIcon />}>
          <Typography variant="body1" gutterBottom>
            No approved objectives found for this scan.
          </Typography>
          <Typography variant="body2">
            Objectives must be extracted and approved before they appear in coverage view.
          </Typography>
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 2 }}>
      {/* Statistics Summary */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
            <Typography variant="h6">Objectives Coverage Summary</Typography>
            <Tooltip title="Refresh">
              <IconButton onClick={handleRefresh} size="small">
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
          
          <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            <Box>
              <Typography variant="body2" color="textSecondary">
                Total Objectives
              </Typography>
              <Typography variant="h4">{stats.totalObjectives}</Typography>
            </Box>
            
            <Divider orientation="vertical" flexItem />
            
            <Box>
              <Typography variant="body2" color="textSecondary">
                With Controls
              </Typography>
              <Typography variant="h4" color="success.main">
                {stats.objectivesWithControls}
              </Typography>
            </Box>
            
            <Box>
              <Typography variant="body2" color="textSecondary">
                Without Controls
              </Typography>
              <Typography variant="h4" color="warning.main">
                {stats.objectivesWithoutControls}
              </Typography>
            </Box>
            
            <Divider orientation="vertical" flexItem />
            
            <Box>
              <Typography variant="body2" color="textSecondary">
                Total Mappings
              </Typography>
              <Typography variant="h4">{stats.totalMappings}</Typography>
              <Typography variant="caption" color="textSecondary">
                ({stats.primaryMappings} primary)
              </Typography>
            </Box>
            
            <Box>
              <Typography variant="body2" color="textSecondary">
                Avg Confidence
              </Typography>
              <Typography variant="h4" sx={{ color: getConfidenceColor(stats.avgConfidence) }}>
                {formatConfidence(stats.avgConfidence)}
              </Typography>
            </Box>
          </Box>
        </CardContent>
      </Card>

      {/* Objectives List */}
      <Typography variant="h6" gutterBottom>
        Objectives & Linked Controls
      </Typography>
      
      {objectives.map((objective) => {
        const controls = objectiveControls.get(objective.id) || [];
        const primaryControl = controls.find((c) => c.is_primary);
        
        return (
          <Accordion
            key={objective.id}
            expanded={expandedObjective === objective.id}
            onChange={handleAccordionChange(objective.id)}
            sx={{ mb: 1 }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%', pr: 2 }}>
                <Box sx={{ flex: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                    <Typography variant="subtitle2" fontWeight="bold">
                      {objective.objective_id}
                    </Typography>
                    <Chip
                      label={formatConfidence(objective.final_confidence)}
                      size="small"
                      sx={{
                        bgcolor: getConfidenceColor(objective.final_confidence),
                        color: 'white',
                        fontWeight: 'bold',
                        height: 20,
                        fontSize: '0.7rem',
                      }}
                    />
                    {objective.category && (
                      <Chip label={objective.category} size="small" variant="outlined" sx={{ height: 20, fontSize: '0.7rem' }} />
                    )}
                  </Box>
                  <Typography variant="body2" color="textSecondary" noWrap>
                    {objective.objective_text}
                  </Typography>
                </Box>
                
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {controls.length > 0 ? (
                    <>
                      <Chip
                        icon={<LinkIcon />}
                        label={`${controls.length} control${controls.length !== 1 ? 's' : ''}`}
                        size="small"
                        color="primary"
                        variant="outlined"
                      />
                      <CheckCircleIcon color="success" fontSize="small" />
                    </>
                  ) : (
                    <>
                      <Chip label="No controls" size="small" color="warning" variant="outlined" />
                      <ErrorIcon color="warning" fontSize="small" />
                    </>
                  )}
                </Box>
              </Box>
            </AccordionSummary>
            
            <AccordionDetails>
              <Box sx={{ pl: 2 }}>
                <Typography variant="body2" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>
                  {objective.objective_text}
                </Typography>
                
                {objective.page_refs && objective.page_refs.length > 0 && (
                  <Typography variant="caption" color="textSecondary" sx={{ mb: 2, display: 'block' }}>
                    Page References: {objective.page_refs.join(', ')}
                  </Typography>
                )}
                
                {controls.length > 0 ? (
                  <>
                    <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>
                      Linked Controls ({controls.length})
                    </Typography>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                      {controls.map((control) => (
                        <Card
                          key={control.mapping_id}
                          variant="outlined"
                          sx={{
                            cursor: onOpenControlModal ? 'pointer' : 'default',
                            '&:hover': onOpenControlModal ? { bgcolor: 'action.hover' } : {},
                          }}
                          onClick={() => handleControlClick(control)}
                        >
                          <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                              <Typography variant="body2" fontWeight="bold">
                                {control.control_id}
                              </Typography>
                              {control.is_primary && (
                                <Chip label="Primary" size="small" color="primary" sx={{ height: 18, fontSize: '0.65rem' }} />
                              )}
                              <Chip
                                label={`${Math.round((control.mapping_confidence || 0) * 100)}% mapping confidence`}
                                size="small"
                                sx={{
                                  bgcolor: getConfidenceColor(control.mapping_confidence),
                                  color: 'white',
                                  height: 18,
                                  fontSize: '0.65rem',
                                }}
                              />
                              {control.control_confidence && (
                                <Chip
                                  label={`${control.control_confidence} control confidence`}
                                  size="small"
                                  variant="outlined"
                                  sx={{ height: 18, fontSize: '0.65rem' }}
                                />
                              )}
                            </Box>
                            <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
                              {control.control_desc || 'No description'}
                            </Typography>
                          </CardContent>
                        </Card>
                      ))}
                    </Box>
                  </>
                ) : (
                  <Alert severity="warning" icon={<ErrorIcon />} sx={{ mt: 2 }}>
                    This objective has no linked controls. Consider mapping it to relevant controls or converting it to a control.
                  </Alert>
                )}
              </Box>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Box>
  );
};

export default ObjectivesCoverageTab;
