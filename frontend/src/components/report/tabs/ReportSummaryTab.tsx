/**
 * ReportSummaryTab Component
 * 
 * Displays SOC 2 report summary including overview, executive summary, key stats, and timeline.
 */

import React, { useState, useCallback } from 'react';
import { Box, Typography, TextField, Button, Checkbox, FormControlLabel, CircularProgress, IconButton, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from '@mui/material';
import { Edit as EditIcon, Refresh as RefreshIcon, Warning as WarningIcon, HelpOutline as HelpOutlineIcon, Save as SaveIcon } from '@mui/icons-material';
import CompactTimeline from '../../../components/CompactTimeline';
import { formatExecutiveSummaryRich } from '../../../services/report/executiveSummaryFormatter';

interface OverviewFields {
  company: string;
  product: string;
  reportType: string;
  coverageStart: string;
  coverageEnd: string;
  reportDate: string;
  auditor: string;
  scanDate: string;
  isSoxVendor: boolean;
}

interface ReportSummaryTabProps {
  overviewFields: OverviewFields;
  overviewEdit: boolean;
  executiveSummary: any;
  executiveSummaryStale: boolean;
  executiveSummaryLoading: boolean;
  coverageStart: string;
  coverageEnd: string;
  reportDate: string;
  filteredHighConfSubOrgs: any[];
  filteredHighConfCuecs: any[];
  filteredHighConfControls: any[];
  onOverviewFieldChange: (field: string, value: any) => void;
  onSaveOverview: () => Promise<void>;
  onSetOverviewEdit: (edit: boolean) => void;
  onRegenerateExecutiveSummary: () => Promise<void>;
  onSaveExecutiveSummary: (summary: any) => Promise<void>;
  onRescanReport: () => Promise<void>;
  onOpenHelp: () => void;
  formatLocalDateWithTZ: (date: string) => string;
  theme: any;
  textSx: any;
}

export const ReportSummaryTab = React.memo(function ReportSummaryTab({
  overviewFields,
  overviewEdit,
  executiveSummary,
  executiveSummaryStale,
  executiveSummaryLoading,
  coverageStart,
  coverageEnd,
  reportDate,
  filteredHighConfSubOrgs,
  filteredHighConfCuecs,
  filteredHighConfControls,
  onOverviewFieldChange,
  onSaveOverview,
  onSetOverviewEdit,
  onRegenerateExecutiveSummary,
  onSaveExecutiveSummary,
  onRescanReport,
  onOpenHelp,
  formatLocalDateWithTZ,
  theme,
  textSx
}: ReportSummaryTabProps) {
  // Executive summary edit state
  const [summaryEdit, setSummaryEdit] = useState(false);
  const [editedSummary, setEditedSummary] = useState<any>(null);
  
  // Rescan confirmation dialog state
  const [rescanConfirmOpen, setRescanConfirmOpen] = useState(false);

  const handleStartSummaryEdit = useCallback(() => {
    setEditedSummary(executiveSummary);
    setSummaryEdit(true);
  }, [executiveSummary]);

  const handleSaveSummary = useCallback(async () => {
    try {
      await onSaveExecutiveSummary(editedSummary);
      setSummaryEdit(false);
    } catch (err) {
      // Error already shown by parent
    }
  }, [editedSummary, onSaveExecutiveSummary]);

  const handleCancelSummaryEdit = useCallback(() => {
    setEditedSummary(null);
    setSummaryEdit(false);
  }, []);
  
  const handleConfirmRescan = useCallback(async () => {
    setRescanConfirmOpen(false);
    try {
      await onRescanReport();
    } catch (err) {
      // Error already shown by parent
    }
  }, [onRescanReport]);

  // Timeline data
  const timelineEvents = [
    { label: 'Coverage Start', date: coverageStart },
    { label: 'Coverage End', date: coverageEnd },
    { label: 'Report Date', date: reportDate },
  ];

  return (
    <>
      <Typography variant="h4" gutterBottom sx={{ fontSize: 22, mb: 2 }}>
        Overview
      </Typography>

      {/* Overview Section */}
      <Box sx={{ mb: 2 }}>
        {overviewEdit ? (
          <>
            <TextField 
              label="Audited Organization" 
              value={overviewFields.company} 
              onChange={e => onOverviewFieldChange('company', e.target.value)} 
              fullWidth 
              sx={{ mb: 1 }} 
            />
            <TextField 
              label="Product" 
              value={overviewFields.product} 
              onChange={e => onOverviewFieldChange('product', e.target.value)} 
              fullWidth 
              sx={{ mb: 1 }} 
            />
            <TextField 
              select
              label="Report Type" 
              value={overviewFields.reportType || 'SOC2'} 
              onChange={e => onOverviewFieldChange('reportType', e.target.value)} 
              fullWidth 
              sx={{ mb: 1 }}
              SelectProps={{ native: true }}
            >
              <option value="SOC1">SOC 1</option>
              <option value="SOC2">SOC 2</option>
              <option value="COMBINED">SOC 1 + SOC 2 Combined</option>
            </TextField>
            <TextField 
              label="Coverage Start" 
              value={overviewFields.coverageStart} 
              onChange={e => onOverviewFieldChange('coverageStart', e.target.value)} 
              fullWidth 
              sx={{ mb: 1 }} 
            />
            <TextField 
              label="Coverage End" 
              value={overviewFields.coverageEnd} 
              onChange={e => onOverviewFieldChange('coverageEnd', e.target.value)} 
              fullWidth 
              sx={{ mb: 1 }} 
            />
            <TextField 
              label="Report Date" 
              value={overviewFields.reportDate} 
              onChange={e => onOverviewFieldChange('reportDate', e.target.value)} 
              fullWidth 
              sx={{ mb: 1 }} 
            />
            <TextField 
              label="Auditor" 
              value={overviewFields.auditor} 
              onChange={e => onOverviewFieldChange('auditor', e.target.value)} 
              fullWidth 
              sx={{ mb: 1 }} 
            />
            <TextField 
              label="Scan Date" 
              value={overviewFields.scanDate} 
              onChange={e => onOverviewFieldChange('scanDate', e.target.value)} 
              fullWidth 
              sx={{ mb: 1 }} 
            />
            <FormControlLabel 
              control={
                <Checkbox 
                  checked={overviewFields.isSoxVendor} 
                  onChange={e => onOverviewFieldChange('isSoxVendor', e.target.checked)} 
                />
              } 
              label="SOX Vendor (subject to Sarbanes-Oxley compliance)" 
              sx={{ mb: 1 }}
            />
            <Box>
              <Button 
                variant="contained" 
                color="success" 
                onClick={onSaveOverview} 
                sx={{ mt: 1, mr: 1 }}
              >
                Save
              </Button>
              <Button 
                variant="outlined" 
                color="secondary" 
                onClick={() => onSetOverviewEdit(false)} 
                sx={{ mt: 1, mr: 1 }}
              >
                Cancel
              </Button>
              <Button 
                variant="outlined" 
                color="warning"
                onClick={() => setRescanConfirmOpen(true)} 
                sx={{ mt: 1 }}
              >
                Rescan Report
              </Button>
            </Box>
          </>
        ) : (
          <>
            <Typography sx={textSx}>
              <b>Report Type:</b> {overviewFields.reportType || 'SOC2'}
            </Typography>
            <Typography sx={textSx}>
              <b>Audited Organization:</b> {overviewFields.company || '-'}
            </Typography>
            <Typography sx={textSx}>
              <b>Product:</b> {overviewFields.product || '-'}
            </Typography>
            <Typography sx={textSx}>
              <b>Coverage Period:</b> {coverageStart} to {coverageEnd}
            </Typography>
            <Typography sx={textSx}>
              <b>Report Date:</b> {reportDate}
            </Typography>
            <Typography sx={textSx}>
              <b>Auditor:</b> {overviewFields.auditor || '-'}
            </Typography>
            <Typography sx={textSx}>
              <b>Scan Date:</b> {formatLocalDateWithTZ(overviewFields.scanDate)}
            </Typography>
            <Typography sx={textSx}>
              <b>SOX Vendor:</b> {overviewFields.isSoxVendor ? 'Yes' : 'No'}
            </Typography>
            <Button 
              variant="outlined" 
              size="small" 
              startIcon={<EditIcon />} 
              onClick={() => onSetOverviewEdit(true)} 
              sx={{ mt: 1 }}
            >
              Edit
            </Button>
          </>
        )}
      </Box>

      {/* Regenerate Executive Summary Button */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 1 }}>
        <Button
          variant="outlined"
          size="small"
          startIcon={<RefreshIcon />}
          onClick={onRegenerateExecutiveSummary}
          disabled={executiveSummaryLoading}
        >
          Regenerate Executive Summary
        </Button>
      </Box>

      {/* Executive Summary + Key Stats + Timeline (side-by-side layout) */}
      <Box sx={{ mb: 2, display: 'flex', gap: 2 }}>
        {/* Left: Executive Summary */}
        <Box sx={{ flex: 1, minWidth: 0 }} className="content-text">
          {/* Stale Warning */}
          {executiveSummaryStale && (
            <Box sx={{ 
              mb: 1, 
              p: 1.5, 
              backgroundColor: theme.palette.mode === 'dark' ? '#665500' : '#fff3cd', 
              border: '1px solid #ffc107', 
              borderRadius: 1 
            }}>
              <Typography sx={{ 
                fontSize: 13, 
                fontWeight: 500, 
                color: theme.palette.mode === 'dark' ? '#ffeb3b' : '#856404', 
                display: 'flex', 
                alignItems: 'center' 
              }}>
                <WarningIcon sx={{ fontSize: 18, mr: 0.5 }} />
                This executive summary may be outdated due to recent changes. Click "Regenerate Executive Summary" above to update it with the latest data.
              </Typography>
            </Box>
          )}

          {/* Executive Summary Content */}
          <Box className="exec-summary-box content-text">
            {executiveSummaryLoading ? (
              <CircularProgress size={20} />
            ) : summaryEdit ? (
              <>
                <TextField
                  fullWidth
                  multiline
                  rows={15}
                  value={JSON.stringify(editedSummary, null, 2)}
                  onChange={(e) => {
                    try {
                      setEditedSummary(JSON.parse(e.target.value));
                    } catch (err) {
                      // Keep typing even if JSON is invalid temporarily
                    }
                  }}
                  sx={{ mb: 1 }}
                />
                <Box>
                  <Button
                    variant="contained"
                    color="success"
                    startIcon={<SaveIcon />}
                    onClick={handleSaveSummary}
                    sx={{ mr: 1 }}
                  >
                    Save
                  </Button>
                  <Button
                    variant="outlined"
                    color="secondary"
                    onClick={handleCancelSummaryEdit}
                  >
                    Cancel
                  </Button>
                </Box>
              </>
            ) : (
              executiveSummary ? (
                <>
                  <div 
                    className="exec-summary-html" 
                    dangerouslySetInnerHTML={{ 
                      __html: formatExecutiveSummaryRich(executiveSummary, filteredHighConfControls) 
                    }} 
                  />
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<EditIcon />}
                    onClick={handleStartSummaryEdit}
                    sx={{ mt: 1 }}
                  >
                    Edit Summary
                  </Button>
                </>
              ) : (
                <Typography sx={{ fontStyle: 'italic', color: '#888' }}>
                  No executive summary available. Click 'Regenerate Executive Summary' to generate one.
                </Typography>
              )
            )}
          </Box>
        </Box>

        {/* Right: Key Stats + Timeline (stacked) */}
        <Box sx={{ 
          flex: 1, 
          minWidth: 0, 
          display: 'flex', 
          flexDirection: 'column', 
          alignItems: 'center', 
          gap: 1, 
          mt: 1 
        }}>
          {/* Key Stats */}
          <div className="key-stats-title">Key Stats</div>
          <Box className="key-stats-row">
            <Box className="key-stats-half key-stats-left">
              <div className="key-stats-label">Subservice Organizations</div>
              <div className="key-stats-value suborgs-color">
                {filteredHighConfSubOrgs ? filteredHighConfSubOrgs.length : 0}
              </div>
              <div className="key-stats-label">CUECs</div>
              <div className="key-stats-value cuecs-color">
                {filteredHighConfCuecs ? filteredHighConfCuecs.length : 0}
              </div>
              <div className="key-stats-label">Controls Assessed</div>
              <div className="key-stats-value controls-color">
                {filteredHighConfControls ? filteredHighConfControls.length : 0}
              </div>
            </Box>
          </Box>

          {/* Timeline */}
          <Box className="key-stats-row" sx={{ mt: 2, justifyContent: 'center' }}>
            <Box className="key-stats-half key-stats-right" sx={{ alignItems: 'center' }}>
              <div className="timeline-heading">Timeline</div>
              <CompactTimeline 
                events={timelineEvents as any} 
                width={420} 
                boxWidth={280} 
                pillFill="#e6c5f5" 
                textFill="#2b2b2b" 
              />
            </Box>
          </Box>
        </Box>
      </Box>

      {/* Rescan Confirmation Dialog */}
      <Dialog
        open={rescanConfirmOpen}
        onClose={() => setRescanConfirmOpen(false)}
      >
        <DialogTitle>Confirm Report Rescan</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to rescan this report?
            <br /><br />
            <strong>Warning:</strong> This will re-extract all data from the PDF and <strong>overwrite</strong> the following:
            <ul style={{ marginTop: 8, marginBottom: 8 }}>
              <li>All controls and their mappings</li>
              <li>All CUECs (Complementary User Entity Controls)</li>
              <li>Subservice organizations</li>
              <li>Executive summary</li>
              <li>Framework coverage analysis</li>
            </ul>
            Any manual edits, annotations, or verifications you've made will be lost.
            <br /><br />
            The report will be added to the scan queue and processed with the current report type setting.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRescanConfirmOpen(false)} color="secondary">
            Cancel
          </Button>
          <Button onClick={handleConfirmRescan} color="warning" variant="contained">
            Yes, Rescan Report
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
});
