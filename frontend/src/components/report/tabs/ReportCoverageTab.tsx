/**
 * ReportCoverageTab Component (Dynamic Multi-Framework)
 * 
 * Displays framework coverage dynamically for any frameworks present in scan data.
 * Supports all registered frameworks (TSC, COSO, FINANCIAL_ASSERTIONS, etc.)
 */

import React, { useEffect, useState } from 'react';
import { Box, Typography, Tooltip, Popover, Tabs, Tab, Alert, CircularProgress, Accordion, AccordionSummary, AccordionDetails } from '@mui/material';
import { 
  CheckCircle as CheckCircleIcon, 
  Cancel as CancelIcon, 
  Warning as WarningIcon,
  Assignment as AssignmentIcon,
  InfoOutlined as InfoOutlinedIcon,
  ExpandMore as ExpandMoreIcon
} from '@mui/icons-material';
import { PieChart, Pie, Cell, Tooltip as RechartsTooltip } from 'recharts';
import { deduplicateCuecs } from '../../../services/report/reportUtils';
import { ObjectivesCoverageTab } from './ObjectivesCoverageTab';
import { SplitViewLayout } from '../SplitViewLayout';
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
  onOpenCuecModal: (cuec: any) => void;
  onOpenControlModal?: (control: any) => void;
  scanId?: number;
  highConfObjectives?: any[];
  onRefresh?: () => void;
  tocPageOffset?: number;
  onCreateControlForObjective?: (objectiveId: number) => void;
}

export const ReportCoverageTab = React.memo(function ReportCoverageTab({
  highConfControlsForCoverage,
  highConfCuecsFiltered,
  onOpenCuecModal,
  onOpenControlModal,
  scanId,
  highConfObjectives,
  onRefresh,
  tocPageOffset,
  onCreateControlForObjective
}: ReportCoverageTabProps) {
  const [frameworkCriteria, setFrameworkCriteria] = useState<{ [key: string]: FrameworkCriteria }>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState(0);
  const [availableFrameworks, setAvailableFrameworks] = useState<string[]>([]);
  const [controlPopoverAnchor, setControlPopoverAnchor] = useState<{el: HTMLElement, controls: any[]} | null>(null);
  const [cuecPopoverAnchor, setCuecPopoverAnchor] = useState<{el: HTMLElement, cuecs: any[]} | null>(null);
  const [pdfNavigateHandler, setPdfNavigateHandler] = useState<((snippet: string | null, page?: number | null) => void) | null>(null);

  // Fetch framework criteria from backend (static data, fetch once)
  useEffect(() => {
    const fetchCriteria = async () => {
      try {
        setLoading(true);
        const response = await api.get('/framework_criteria');
        setFrameworkCriteria(response.data);
        setLoading(false);
      } catch (err: any) {
        console.error('Failed to load framework criteria:', err);
        setError('Failed to load framework criteria');
        setLoading(false);
      }
    };
    
    fetchCriteria();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-detect available frameworks when controls change (no loading spinner)
  useEffect(() => {
    if (Object.keys(frameworkCriteria).length > 0) {
      detectAvailableFrameworks(frameworkCriteria);
    }
  }, [highConfControlsForCoverage, frameworkCriteria]); // eslint-disable-line react-hooks/exhaustive-deps

  // Detect which frameworks are actually present in the control data
  const detectAvailableFrameworks = (criteria: { [key: string]: FrameworkCriteria }) => {
    const frameworks: string[] = [];
    
    for (const [key, fw] of Object.entries(criteria)) {
      // Check if any controls have this framework mapped (new format)
      let hasData = highConfControlsForCoverage.some((ctrl: any) => {
        const mappings = ctrl.framework_mappings || {};
        return mappings[fw.framework_name] && Array.isArray(mappings[fw.framework_name]) && mappings[fw.framework_name].length > 0;
      });
      
      if (hasData) {
        frameworks.push(key);
      }
    }
    
    setAvailableFrameworks(frameworks);
  };

  // Calculate coverage stats for a framework
  const calculateFrameworkCoverage = (frameworkKey: string) => {
    const fw = frameworkCriteria[frameworkKey];
    if (!fw) return { total: 0, coveredByControls: 0, coveredByCuecs: 0, likelyCovered: 0, missed: 0, idsFound: new Set(), idsByCuecs: new Set(), missingIds: [] };
    
    let total = 0;
    const idsFound = new Set<string>();
    const idsByCuecs = new Set<string>();
    
    // Count all criteria
    Object.values(fw.sections).forEach(criteria => {
      total += criteria.length;
    });
    
    // Scan controls for framework mappings
    highConfControlsForCoverage.forEach((ctrl: any) => {
      const mappings = ctrl.framework_mappings?.[fw.framework_name] || [];
      mappings.forEach((mapping: any) => {
        if (mapping.id) idsFound.add(mapping.id);
      });
    });
    
    // Scan CUECs for framework mappings
    highConfCuecsFiltered.forEach((cuec: any) => {
      const mappings = cuec.framework_mappings?.[fw.framework_name] || [];
      mappings.forEach((mapping: any) => {
        if (mapping.id) idsByCuecs.add(mapping.id);
      });
    });
    
    // Calculate coverage for each criterion
    const uniquelyCovered = new Set<string>();
    let coveredByCuecs = 0;
    let likelyCovered = 0;
    const missingIds: string[] = [];
    
    Object.values(fw.sections).forEach(criteria => {
      criteria.forEach(crit => {
        const isCoveredByControl = idsFound.has(crit.id);
        const isCoveredByCuec = idsByCuecs.has(crit.id);
        
        if (isCoveredByControl || isCoveredByCuec) {
          uniquelyCovered.add(crit.id);
        }
        
        if (isCoveredByCuec) {
          coveredByCuecs++;
        }
        
        if (!isCoveredByControl && !isCoveredByCuec) {
          missingIds.push(crit.id);
        }
      });
    });
    
    const coveredByControls = uniquelyCovered.size;
    const missed = total - coveredByControls;
    
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
            {stats.coveredByControls}/{stats.total} ({stats.total > 0 ? ((stats.coveredByControls/stats.total)*100).toFixed(0) : 0}%)
          </div>

          {/* Framework Alignment Tables */}
          <div className="tsc-coso-align-heading">{fw.display_name} Alignment</div>
          {Object.entries(fw.sections).map(([section, criteria], sectionIndex) => {
            // Calculate section statistics
            const criteriaWithMappings = new Set<string>();
            let sectionCoveredByCuecs = 0;
            let sectionDeviations = 0;
            
            criteria.forEach((crit: any) => {
              const isCovered = stats.idsFound.has(crit.id);
              const isCuecCovered = stats.idsByCuecs.has(crit.id);
              
              // Track unique criteria that have at least one mapping (control or CUEC)
              if (isCovered || isCuecCovered) {
                criteriaWithMappings.add(crit.id);
              }
              
              if (isCuecCovered) sectionCoveredByCuecs++;
              
              // Check for deviations in mapped controls
              const mappedControls = highConfControlsForCoverage.filter((c: any) => {
                const mappings = c.framework_mappings?.[fw.framework_name] || [];
                return mappings.some((m: any) => m.id === crit.id);
              });
              
              const hasDeviation = mappedControls.some((c: any) => 
                c.has_deviation === true && typeof c.deviation_desc === 'string' && c.deviation_desc.trim()
              );
              if (hasDeviation) sectionDeviations++;
            });
            
            const sectionTotal = criteria.length;
            const sectionMapped = criteriaWithMappings.size;
            
            return (
              <Accordion key={section} defaultExpanded={sectionIndex === 0} sx={{ mb: 1, boxShadow: 1 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ bgcolor: 'grey.50', '&:hover': { bgcolor: 'grey.100' } }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', pr: 2 }}>
                    <Typography sx={{ fontWeight: 600, fontSize: 14 }}>{section}</Typography>
                    <Box sx={{ display: 'flex', gap: 2, fontSize: 12, color: 'text.secondary' }}>
                      <span><strong>{sectionMapped}/{sectionTotal}</strong> mapped</span>
                      {sectionCoveredByCuecs > 0 && <span style={{ color: '#9c27b0' }}><strong>{sectionCoveredByCuecs}</strong> CUECs</span>}
                      {sectionDeviations > 0 && <span style={{ color: '#d32f2f' }}><strong>{sectionDeviations}</strong> deviations</span>}
                    </Box>
                  </Box>
                </AccordionSummary>
                <AccordionDetails sx={{ p: 0 }}>
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
                        const isCovered = stats.idsFound.has(crit.id);
                        const isCuecCovered = stats.idsByCuecs.has(crit.id);
                        
                        // Collect controls that map to this criterion
                        const mappedControls = highConfControlsForCoverage.filter((c: any) => {
                          const mappings = c.framework_mappings?.[fw.framework_name] || [];
                          return mappings.some((m: any) => m.id === crit.id);
                        });
                        
                        // Collect CUECs that map to this criterion
                        const mappedCuecs = highConfCuecsFiltered.filter((cuec: any) => {
                          const mappings = cuec.framework_mappings?.[fw.framework_name] || [];
                          return mappings.some((m: any) => m.id === crit.id);
                        });
                        
                        const devList = mappedControls
                          .filter((c: any) => c.has_deviation === true && typeof c.deviation_desc === 'string' && c.deviation_desc.trim())
                          .map((c: any) => c.deviation_desc);
                        const hasDev = devList.length > 0;

                        return (
                          <tr key={crit.id} className={hasDev ? 'tsc-coso-row-exception' : ''}>
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
                                {/* Primary coverage icon - green check for controls, purple for CUEC-only, red X for missed */}
                                {isCovered ? (
                                  <CheckCircleIcon sx={{ color: '#4caf50', fontSize: 18 }} />
                                ) : isCuecCovered ? (
                                  <Tooltip title="Covered by CUEC only">
                                    <AssignmentIcon sx={{ color: '#9c27b0', fontSize: 18 }} />
                                  </Tooltip>
                                ) : (
                                  <CancelIcon sx={{ color: '#e57373', fontSize: 18 }} />
                                )}
                                
                                {/* Deviation warning icon - red warning if any mapped controls have deviations */}
                                {hasDev && (
                                  <Tooltip title={<span style={{ whiteSpace: 'pre-line' }}>{devList.join('\n')}</span>}>
                                    <WarningIcon sx={{ color: '#d32f2f', fontSize: 18, cursor: 'pointer' }} />
                                  </Tooltip>
                                )}
                                
                                {/* Info icon for controls - click to see list */}
                                {mappedControls.length > 0 && (
                                  <InfoOutlinedIcon 
                                    sx={{ color: '#1976d2', fontSize: 16, cursor: 'pointer', ml: 0.5 }} 
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setControlPopoverAnchor({el: e.currentTarget.parentElement as HTMLElement, controls: mappedControls});
                                    }}
                                  />
                                )}
                                
                                {/* CUEC icon - purple, click to see list */}
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
                </AccordionDetails>
              </Accordion>
            );
          })}
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

  // Total number of sub-tabs = frameworks + objective coverage (if scanId present)
  const hasObjectiveCoverage = scanId !== undefined;
  const totalTabs = availableFrameworks.length + (hasObjectiveCoverage ? 1 : 0);
  const objectiveCoverageTabIndex = availableFrameworks.length;
  const isObjectivesTab = selectedTab === objectiveCoverageTabIndex && hasObjectiveCoverage;

  const mainContent = (
    <>
      <Typography variant="h5" gutterBottom sx={{ fontSize: 18, mb: 2 }}>
        Coverage
      </Typography>

      {totalTabs > 1 && (
        <Tabs value={selectedTab} onChange={(e, newValue) => setSelectedTab(newValue)} sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}>
          {availableFrameworks.map((fwKey, index) => (
            <Tab key={fwKey} label={frameworkCriteria[fwKey]?.display_name || fwKey.toUpperCase()} />
          ))}
          {hasObjectiveCoverage && (
            <Tab label="Objective Coverage" />
          )}
        </Tabs>
      )}

      <Box sx={{ height: 'calc(100vh - 350px)', overflow: 'auto', pr: 1, minWidth: 0 }}>
        {isObjectivesTab ? (
          <ObjectivesCoverageTab
            scanId={scanId!}
            objectives={highConfObjectives || []}
            allControls={highConfControlsForCoverage}
            onRefresh={onRefresh}
            tocPageOffset={tocPageOffset}
            pdfNavigateHandler={pdfNavigateHandler}
            onCreateControlForObjective={onCreateControlForObjective}
          />
        ) : availableFrameworks.length > 0 && selectedTab < availableFrameworks.length ? (
          renderFrameworkSection(availableFrameworks[selectedTab])
        ) : !hasObjectiveCoverage ? (
          <Alert severity="info">No framework coverage data available</Alert>
        ) : null}
      </Box>
    </>
  );

  return (
    <>
      {isObjectivesTab ? (
        <SplitViewLayout
          scanId={scanId || 0}
          tabName="objectives"
          onPdfNavigate={(handler) => setPdfNavigateHandler(() => handler)}
        >
          {mainContent}
        </SplitViewLayout>
      ) : (
        mainContent
      )}


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
