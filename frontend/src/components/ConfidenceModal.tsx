import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Collapse,
  IconButton,
  Divider
} from '@mui/material';
import {
  Psychology as GptIcon,
  Pattern as PatternIcon,
  AccountTree as StructureIcon,
  Hub as FrameworkIcon,
  Warning as DeviationIcon,
  CheckCircle as CheckIcon,
  Cancel as CancelIcon,
  Help as HelpIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon
} from '@mui/icons-material';

interface ConfidenceModalProps {
  open: boolean;
  control: any;
  onClose: () => void;
  onOpenControlDetails?: (control: any) => void;
}

const ConfidenceModal: React.FC<ConfidenceModalProps> = ({ open, control, onClose, onOpenControlDetails }) => {
  const [showHistory, setShowHistory] = React.useState(false);

  if (!control) return null;

  const metadata = control?.verification_metadata || {};
  const factorScores = metadata.factor_scores || {};
  const weightedContributions = metadata.weighted_contributions || {};
  const weightsUsed = metadata.weights_used || {};
  const finalConfidence = metadata.final_confidence || control.final_confidence || 0.5;
  const method = metadata.method || 'legacy';
  const calculatedAt = metadata.calculated_at;
  const history = metadata.history || [];

  // If no 5-factor metadata
  if (method !== '5-factor' || Object.keys(factorScores).length === 0) {
    return (
      <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle>Confidence Details</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            This control was extracted before the 5-factor confidence system was implemented.
            Only basic confidence scores are available.
          </Typography>
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2">
              <strong>GPT Confidence:</strong> {((control.control_confidence || 0.5) * 100).toFixed(0)}%
            </Typography>
            {control.pattern_confidence !== null && control.pattern_confidence !== undefined && (
              <Typography variant="body2">
                <strong>Pattern Confidence:</strong> {(control.pattern_confidence * 100).toFixed(0)}%
              </Typography>
            )}
            <Typography variant="body2">
              <strong>Final Confidence:</strong> {(finalConfidence * 100).toFixed(0)}%
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Close</Button>
        </DialogActions>
      </Dialog>
    );
  }

  const factors = [
    {
      key: 'gpt',
      label: 'GPT Quality',
      icon: <GptIcon />,
      score: factorScores.gpt_confidence || 0,
      weight: weightsUsed.gpt_weight || 0.25,
      contribution: weightedContributions.gpt_contribution || 0,
      explanation: 'Base extraction quality from GPT model'
    },
    {
      key: 'pattern',
      label: 'Pattern Match',
      icon: <PatternIcon />,
      score: factorScores.pattern_confidence || 0,
      weight: weightsUsed.pattern_weight || 0.20,
      contribution: weightedContributions.pattern_contribution || 0,
      explanation: 'ID pattern recognition from learned patterns'
    },
    {
      key: 'structure',
      label: 'Structure',
      icon: <StructureIcon />,
      score: factorScores.structure_score || 0,
      weight: weightsUsed.structure_weight || 0.20,
      contribution: weightedContributions.structure_contribution || 0,
      explanation: 'Presence of key fields (test, results, description)'
    },
    {
      key: 'framework',
      label: 'Framework',
      icon: <FrameworkIcon />,
      score: factorScores.framework_score || 0,
      weight: weightsUsed.framework_weight || 0.20,
      contribution: weightedContributions.framework_contribution || 0,
      explanation: 'Quality of TSC/COSO framework mappings'
    },
    {
      key: 'deviation',
      label: 'Deviation',
      icon: <DeviationIcon />,
      score: factorScores.deviation_score || 0,
      weight: weightsUsed.deviation_weight || 0.15,
      contribution: weightedContributions.deviation_contribution || 0,
      explanation: 'Consistency between deviation flag and description'
    }
  ];

  const getStatusIcon = (score: number) => {
    if (score >= 0.7) return <CheckIcon color="success" fontSize="small" />;
    if (score >= 0.5) return <HelpIcon color="warning" fontSize="small" />;
    return <CancelIcon color="error" fontSize="small" />;
  };

  const getScoreColor = (score: number) => {
    if (score < 0.5) return 'error';
    if (score < 0.7) return 'warning';
    return 'success';
  };

  // Calculate gauge color gradient
  const getGaugeColor = (conf: number) => {
    if (conf < 0.5) return '#f44336'; // error red
    if (conf < 0.7) return '#ff9800'; // warning orange
    return '#4caf50'; // success green
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h6">Confidence Analysis</Typography>
          <Chip 
            label={`Control ${control.control_id || 'N/A'}`} 
            size="small" 
            variant="outlined"
            onClick={onOpenControlDetails ? () => onOpenControlDetails(control) : undefined}
            sx={{ 
              cursor: onOpenControlDetails ? 'pointer' : 'default',
              '&:hover': onOpenControlDetails ? { bgcolor: 'action.hover' } : {}
            }}
          />
        </Box>
      </DialogTitle>
      
      <DialogContent>
        {/* Header: Final Confidence Gauge */}
        <Box sx={{ 
          textAlign: 'center', 
          py: 1.5, 
          mb: 1.5,
          background: `linear-gradient(135deg, ${getGaugeColor(finalConfidence)}22 0%, ${getGaugeColor(finalConfidence)}11 100%)`,
          borderRadius: 2
        }}>
          <Typography variant="h4" sx={{ 
            fontWeight: 'bold',
            color: getGaugeColor(finalConfidence),
            mb: 0.5,
            fontSize: '1.75rem'
          }}>
            {(finalConfidence * 100).toFixed(1)}%
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '12px' }}>
            Final Confidence Score
          </Typography>
          <Chip 
            label={finalConfidence >= 0.5 ? 'VERIFIED' : 'PENDING REVIEW'}
            color={finalConfidence >= 0.5 ? 'success' : 'warning'}
            sx={{ mt: 0.5 }}
            size="small"
          />
        </Box>

        {/* Factor Breakdown Table */}
        <Typography variant="body2" sx={{ mb: 1, fontWeight: 'bold', fontSize: '12px' }}>
          Factor Breakdown
        </Typography>
        
        <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Factor</TableCell>
                <TableCell align="center">Weight</TableCell>
                <TableCell align="center">Raw Score</TableCell>
                <TableCell align="center">Contribution</TableCell>
                <TableCell align="center">Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {factors.map((factor) => (
                <TableRow key={factor.key}>
                  <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {factor.icon}
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 500, fontSize: '11px' }}>
                        {factor.label}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '10px' }}>
                        {factor.explanation}
                      </Typography>
                      </Box>
                    </Box>
                  </TableCell>
                  <TableCell align="center">
                    <Chip 
                      label={`${(factor.weight * 100).toFixed(0)}%`}
                      size="small"
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell align="center">
                    <Chip 
                      label={`${(factor.score * 100).toFixed(0)}%`}
                      size="small"
                      color={getScoreColor(factor.score)}
                    />
                  </TableCell>
                  <TableCell align="center">
                    <Typography variant="body2" sx={{ fontWeight: 'bold', fontSize: '11px' }}>
                      {factor.contribution.toFixed(3)}
                    </Typography>
                  </TableCell>
                  <TableCell align="center">
                    {getStatusIcon(factor.score)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {/* Calculation Details */}
        <Typography variant="body2" sx={{ mb: 1, fontWeight: 'bold', fontSize: '12px' }}>
          Calculation Formula
        </Typography>
        
        <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5, backgroundColor: 'action.hover' }}>
          <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '11px' }}>
            final_confidence = 
          </Typography>
          {factors.map((factor, idx) => (
            <Typography 
              key={factor.key}
              variant="body2" 
              sx={{ fontFamily: 'monospace', fontSize: '11px', ml: 2 }}
            >
              {idx > 0 && '+ '}
              ({factor.weight.toFixed(2)} × {factor.score.toFixed(3)})
              {idx < factors.length - 1 ? '' : ` = ${finalConfidence.toFixed(3)}`}
            </Typography>
          ))}
        </Paper>

        {/* Metadata Section */}
        <Typography variant="body2" sx={{ mb: 1, fontWeight: 'bold', fontSize: '12px' }}>
          Metadata
        </Typography>
        
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '11px' }}>
            <strong>Method:</strong> {method}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '11px' }}>
            <strong>Calculated:</strong> {calculatedAt ? new Date(calculatedAt).toLocaleString() : 'N/A'}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '11px' }}>
            <strong>Weights Snapshot:</strong> GPT {(weightsUsed.gpt_weight || 0.25) * 100}%, 
            Pattern {(weightsUsed.pattern_weight || 0.20) * 100}%, 
            Structure {(weightsUsed.structure_weight || 0.20) * 100}%, 
            Framework {(weightsUsed.framework_weight || 0.20) * 100}%, 
            Deviation {(weightsUsed.deviation_weight || 0.15) * 100}%
          </Typography>
        </Box>

        {/* History Section */}
        {history.length > 0 && (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 'bold', flex: 1, fontSize: '12px' }}>
                Calculation History
              </Typography>
              <IconButton size="small" onClick={() => setShowHistory(!showHistory)}>
                {showHistory ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              </IconButton>
            </Box>
            
            <Collapse in={showHistory}>
              <Paper variant="outlined" sx={{ p: 1.5, mb: 1 }}>
                {history.map((entry: any, idx: number) => (
                  <Box key={idx} sx={{ mb: idx < history.length - 1 ? 1 : 0 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontSize: '10px' }}>
                      {new Date(entry.calculated_at).toLocaleString()} - 
                      Final: {(entry.final_confidence * 100).toFixed(1)}%
                    </Typography>
                    {idx < history.length - 1 && <Divider sx={{ mt: 1 }} />}
                  </Box>
                ))}
              </Paper>
            </Collapse>
          </>
        )}
      </DialogContent>
      
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button variant="contained" onClick={() => {
          // TODO: Navigate to review page
          console.log('Open review for control:', control.id);
        }}>
          Open Review
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ConfidenceModal;
