/**
 * ReportCoverageTab Component (Dynamic Multi-Framework Version)
 * 
 * Displays framework coverage dynamically based on available frameworks in scan data.
 * Supports TSC, COSO, FINANCIAL_ASSERTIONS, and future frameworks.
 */

import React, { useEffect, useState } from 'react';
import { Box, Typography, Tooltip, Popover, IconButton, Tabs, Tab, Alert, CircularProgress } from '@mui/material';
import { 
  CheckCircle as CheckCircleIcon, 
  Cancel as CancelIcon, 
  Warning as WarningIcon,
  Assignment as AssignmentIcon,
  InfoOutlined as InfoOutlinedIcon
} from '@mui/icons-material';
import { PieChart, Pie, Cell, Tooltip as RechartsTooltip } from 'recharts';
import { parseMapping } from '../../../services/report/dataTransformations';
import { deduplicateCuecs } from '../../../services/report/reportUtils';
import api from '../../../api/client';

interface FrameworkCriteria {
  framework_name: string;
  display_name: string;
  sections: { [section: string]: Array<{ id: string; description: string; name?: string }> };
  color: string;
  icon: string;
}

interface ReportCoverageTabProps {
  highConfControlsForCoverage: any[];
  highConfCuecsFiltered: any[];
  getCoverageStatus: (
    frameworkId: any, 
    controls: any[], 
    idKey: string, 
    missingIds: string[], 
    cuecIds: Set<string>
  ) => {
    covered: boolean;
    exception: boolean;
    cuecCovered: boolean;
    likelyCovered: boolean;
    coverageType: string;
  };
  onOpenCuecModal: (cuec: any) => void;
  onOpenControlModal?: (control: any) => void;
}

export const ReportCoverageTab = React.memo(function ReportCoverageTab({
  highConfControlsForCoverage,
  highConfCuecsFiltered,
  getCoverageStatus,
  onOpenCuecModal,
  onOpenControlModal
}: ReportCoverageTabProps) {
  const [frameworkCriteria, setFrameworkCriteria] = useState<{ [key: string]: FrameworkCriteria }>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState(0);
  const [availableFrameworks, setAvailableFrameworks] = useState<string[]>([]);
  
  const [controlPopoverAnchor, setControlPopoverAnchor] = React.useState<{el: HTMLElement, controls: any[]} | null>(null);
  const [cuecPopoverAnchor, setCuecPopoverAnchor] = React.useState<{el: HTMLElement, cuecs: any[]} | null>(null);

  // Fetch framework criteria from backend
  useEffect(() => {
    const fetchCriteria = async () => {
      try {
        setLoading(true);
        const response = await api.get('/framework_criteria');
        setFrameworkCriteria(response.data);
        
        // Detect which frameworks have data in controls
        detectAvailableFrameworks(response.data);
        setLoading(false);
      } catch (err: any) {
        console.error('Failed to load framework criteria:', err);
        setError('Failed to load framework criteria');
        setLoading(false);
      }
    };
    
    fetchCriteria();
  }, []);

  // Detect which frameworks are actually present in the control data
  const detectAvailableFrameworks = (criteria: { [key: string]: FrameworkCriteria }) => {
    const frameworks: string[] = [];
    
    for (const [key, fw] of Object.entries(criteria)) {
      // Check if any controls have this framework mapped
      const hasData = highConfControlsForCoverage.some((ctrl: any) => {
        const mappings = ctrl.framework_mappings || {};
        return mappings[fw.framework_name]  && Array.isArray(mappings[fw.framework_name]) && mappings[fw.framework_name].length > 0;
      });
      
      if (hasData) {
        frameworks.push(key);
      }
    }
    
    // Default to TSC and COSO if nothing detected (backward compatibility)
    if (frameworks.length === 0) {
      frameworks.push('tsc', 'coso');
    }
    
    setAvailableFrameworks(frameworks);
  };

  // Calculate coverage stats for a framework
  const calculateFrameworkCoverage = (frameworkKey: string) => {
    const fw = frameworkCriteria[frameworkKey];
    if (!fw) return { total: 0, coveredByControls: 0, coveredByCuecs: 0, likelyCovered: 0, missed: 0 };
    
    let total = 0;
    let coveredByControls = 0;
    let coveredByCuecs = 0;
    let likelyCovered = 0;
    let missed = 0;
    
    // Count all criteria
    Object.values(fw.sections).forEach(criteria => {
      total += criteria.length;
    });
    
    // Collect IDs found in controls and CUECs
    const idsFound = new Set<string>();
    const idsByCuecs = new Set<string>();
    const missingIds: string[] = [];
    
    // Scan controls for framework mappings
    highConfControlsForCoverage.forEach((ctrl: any) => {
      const mappings = ctrl.framework_mappings?.[fw.framework_name] || [];
      mappings.forEach((mapping: any) => {
        idsFound.add(mapping.id);
      });
    });
    
    // Scan CUECs for framework mappings
    highConfCuecsFiltered.forEach((cuec: any) => {
      const mappings = cuec.cuec_framework_mappings?.[fw.framework_name] || [];
      mappings.forEach((mapping: any) => {
        idsByCuecs.add(mapping.id);
      });
    });
    
    // Calculate coverage for each criterion
    Object.values(fw.sections).forEach(criteria => {
      criteria.forEach(crit => {
        const { coverageType } = getCoverageStatus(
          crit.id,
          highConfControlsForCoverage,
          `control_${frameworkKey}_id`,
          missingIds,
          idsByCuecs
        );
        
        if (coverageType === 'control') coveredByControls++;
        else if (coverageType === 'cuec') coveredByCuecs++;
        else if (coverageType === 'likely') likelyCovered++;
        else missed++;
      });
    });
    
    return { total, coveredByControls, coveredByCuecs, likelyCovered, missed, idsFound, idsByCuecs, missingIds };
  };

  // Donut chart data generator
  const donutDataFourCategories = (
    controlsCovered: number, 
    cuecsCovered: number, 
    likelyCovered: number, 
    missed: number
  ) => [
    { name: 'Covered', value: controlsCovered },
    { name: 'CUEC', value: cuecsCovered },
    { name: 'Likely Covered', value: likelyCovered },
    { name: 'Missed', value: missed },
  ];

  const donutColorsFourCategories = ['#4caf50', '#9c27b0', '#ff9800', '#e57373'];

  // Render a single framework's coverage section
  const renderFrameworkSection = (frameworkKey: string) => {
    const fw = frameworkCriteria[frameworkKey];
    if (!fw) return null;
    
    const stats = calculateFrameworkCoverage(frameworkKey);
    
    return (
      <Box key={frameworkKey}>
        <Box className="tsc-coso-half" sx={{ width: '100%', maxWidth: 'none' }}>
          <div className="tsc-coso-donut-title">{fw.display_name} Coverage</div>
          <div className="tsc-coso-donut-wrapper">
            <PieChart width={140} height={140}>
              <Pie 
                data={donutDataFourCategories(stats.coveredByControls, stats.coveredByCuecs, stats.likelyCovered, stats.missed)} 
                dataKey="value" 
                nameKey="name" 
                cx="50%" 
                cy="50%" 
                innerRadius={38} 
                outerRadius={60} 
                label={false}
              >
                {donutDataFourCategories(stats.coveredByControls, stats.coveredByCuecs, stats.likelyCovered, stats.missed).map((entry: any, idx: number) => (
                  <Cell key={idx} fill={donutColorsFourCategories[idx]} />
                ))}
              </Pie>
              <RechartsTooltip formatter={(value: any, name: any) => [`${value} items`, name]} />
            </PieChart>
            <div className="tsc-coso-donut-legend">
              <span className="legend-covered" /> Covered
              <span className="legend-cuec" style={{ backgroundColor: '#9c27b0' }} /> CUEC
              <span className="legend-likely-covered" style={{ backgroundColor: '#ff9800' }} /> Likely Covered
              <span className="legend-missing" /> Missed
            </div>
          </div>
          <div className="tsc-coso-donut-value">
            {stats.coveredByControls + stats.coveredByCuecs}/{stats.total} ({(((stats.coveredByControls + stats.coveredByCuecs)/stats.total)*100).toFixed(0)}%)
          </div>

          {/* Framework Alignment Tables */}
          <div className="tsc-coso-align-heading">{fw.display_name} Alignment</div>
          {Object.entries(fw.sections).map(([section, criteria]) => (
            <div key={section} className="tsc-coso-section-block">
              <div className="tsc-coso-section-title">{section}</div>
              <table className="tsc-coso-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Description</th>
                    <th>Covered</th>
                  </tr>
                </thead>
                <tbody>
                  {criteria.map((crit: any) => {
                    const { exception, coverageType } = getCoverageStatus(
                      crit.id, 
                      highConfControlsForCoverage, 
                      `control_${frameworkKey}_id`, 
                      stats.missingIds, 
                      stats.idsByCuecs
                    );
                    
                    // Collect controls that map to this criterion
                    const mappedControls = highConfControlsForCoverage.filter((c: any) => {
                      const mappings = c.framework_mappings?.[fw.framework_name] || [];
                      return mappings.some((m: any) => m.id === crit.id);
                    });
                    
                    // Collect CUECs that map to this criterion
                    const mappedCuecs = highConfCuecsFiltered.filter((cuec: any) => {
                      const mappings = cuec.cuec_framework_mappings?.[fw.framework_name] || [];
                      return mappings.some((m: any) => m.id === crit.id);
                    });
                    
                    const devList = mappedControls
                      .filter((c: any) => c.has_deviation === true && typeof c.deviation_desc === 'string' && c.deviation_desc.trim())
                      .map((c: any) => c.deviation_desc);
                    const hasDev = devList.length > 0;

                    return (
                      <tr key={crit.id} className={(exception || hasDev) ? 'tsc-coso-row-exception' : ''}>
                        <td>{crit.id}</td>
                        <td>
                          {hasDev ? (
                            <Tooltip title={<span style={{ whiteSpace: 'pre-line' }}>{devList.join('\n')}</span>}>
                              <span>{crit.description}</span>
                            </Tooltip>
                          ) : (
                            crit.description
                          )}
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                            {coverageType === 'control' ? (
                              <CheckCircleIcon sx={{ color: '#4caf50', fontSize: 18 }} />
                            ) : coverageType === 'cuec' ? (
                              <Tooltip title="Covered by CUEC">
                                <AssignmentIcon sx={{ color: '#9c27b0', fontSize: 18 }} />
                              </Tooltip>
                            ) : coverageType === 'likely' ? (
                              <Tooltip title="Likely covered under another control - found in extracted text">
                                <WarningIcon sx={{ color: '#ff9800', fontSize: 18 }} />
                              </Tooltip>
                            ) : (
                              <CancelIcon sx={{ color: '#e57373', fontSize: 18 }} />
                            )}
                            {mappedControls.length > 0 && (
                              <InfoOutlinedIcon 
                                sx={{ color: '#1976d2', fontSize: 16, cursor: 'pointer', ml: 0.5 }} 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setControlPopoverAnchor({el: e.currentTarget.parentElement as HTMLElement, controls: mappedControls});
                                }}
                              />
                            )}
                            {mappedCuecs.length > 0 && (
                              <AssignmentIcon 
                                sx={{ color: '#9c27b0', fontSize: 16, cursor: 'pointer' }} 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setCuecPopoverAnchor({el: e.currentTarget.parentElement as HTMLElement, cuecs: deduplicateCuecs(mappedCuecs)});
                                }}
                              />
                            )}
                          </Box>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}
        </Box>
      </Box>
    );
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', p: 4 }}>
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>Loading framework criteria...</Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ m: 2 }}>
        {error}
      </Alert>
    );
  }

  return (
    <>
      <Typography variant="h5" gutterBottom sx={{ fontSize: 18, mb: 2 }}>
        Framework Coverage
      </Typography>

      {availableFrameworks.length > 1 && (
        <Tabs value={selectedTab} onChange={(e, newValue) => setSelectedTab(newValue)} sx={{ mb: 2 }}>
          {availableFrameworks.map((fwKey, index) => (
            <Tab key={fwKey} label={frameworkCriteria[fwKey]?.display_name || fwKey.toUpperCase()} />
          ))}
        </Tabs>
      )}

      <Box>
        {availableFrameworks.length > 0 ? (
          renderFrameworkSection(availableFrameworks[selectedTab])
        ) : (
          <Alert severity="info">No framework coverage data available</Alert>
        )}
      </Box>

      {/* Control Popover */}
      <Popover
        open={Boolean(controlPopoverAnchor)}
        anchorEl={controlPopoverAnchor?.el}
        onClose={() => setControlPopoverAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        transformOrigin={{ vertical: 'top', horizontal: 'left' }}
      >
        <Box sx={{ p: 0.5 }}>
          <Box sx={{ fontSize: '12px', fontWeight: 'bold', mb: 0.5 }}>
            Controls ({controlPopoverAnchor?.controls.length || 0}):
          </Box>
          <Box component="ul" sx={{ m: '4px 0', pl: '20px', fontSize: '11px' }}>
            {controlPopoverAnchor?.controls.map((c: any) => (
              <Box
                component="li"
                key={c.id}
                sx={{ 
                  cursor: onOpenControlModal ? 'pointer' : 'default', 
                  textDecoration: onOpenControlModal ? 'underline' : 'none',
                  '&:hover': onOpenControlModal ? { bgcolor: 'action.hover' } : {},
                }}
                onClick={onOpenControlModal ? () => {
                  onOpenControlModal(c);
                  setControlPopoverAnchor(null);
                } : undefined}
              >
                {c.control_id || `Control ${c.id}`}
              </Box>
            ))}
          </Box>
        </Box>
      </Popover>

      {/* CUEC Popover */}
      <Popover
        open={Boolean(cuecPopoverAnchor)}
        anchorEl={cuecPopoverAnchor?.el}
        onClose={() => setCuecPopoverAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        transformOrigin={{ vertical: 'top', horizontal: 'left' }}
      >
        <Box sx={{ p: 0.5 }}>
          <Box sx={{ fontSize: '12px', fontWeight: 'bold', mb: 0.5 }}>
            CUECs ({cuecPopoverAnchor?.cuecs.length || 0}):
          </Box>
          <Box component="ul" sx={{ m: '4px 0', pl: '20px', fontSize: '11px' }}>
            {cuecPopoverAnchor?.cuecs.map((cuec: any) => (
              <Box
                key={cuec.id}
                component="li"
                sx={{
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  '&:hover': { bgcolor: 'action.hover' },
                }}
                onClick={() => {
                  onOpenCuecModal(cuec);
                  setCuecPopoverAnchor(null);
                }}
              >
                {(cuec.cuec_description || cuec.cuec_id || `CUEC ${cuec.id}`).substring(0, 60)}
                {((cuec.cuec_description || '').length > 60) ? '...' : ''}
              </Box>
            ))}
          </Box>
        </Box>
      </Popover>
    </>
  );
});
