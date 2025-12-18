import React from 'react';
import {
  Tooltip,
  Box,
  Typography,
  LinearProgress,
  Paper,
  Popper,
  Link
} from '@mui/material';
import {
  Psychology as GptIcon,
  Pattern as PatternIcon,
  AccountTree as StructureIcon,
  Hub as FrameworkIcon,
  Warning as DeviationIcon
} from '@mui/icons-material';

interface ConfidenceTooltipProps {
  control: any;
  children: React.ReactElement;
  onClick?: () => void;
}

const ConfidenceTooltip: React.FC<ConfidenceTooltipProps> = ({ control, children, onClick }) => {
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);

  const handleMouseEnter = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMouseLeave = () => {
    setAnchorEl(null);
  };

  const handleClick = (e: React.MouseEvent) => {
    console.log('[ConfidenceTooltip] Click detected, onClick prop exists:', !!onClick);
    e.stopPropagation();
    setAnchorEl(null);
    if (onClick) {
      console.log('[ConfidenceTooltip] Calling onClick handler');
      onClick();
    }
  };

  // Extract factor scores from verification_metadata
  const metadata = control?.verification_metadata || {};
  const factorScores = metadata.factor_scores || {};
  const method = metadata.method || 'legacy';

  // If no 5-factor metadata, show N/A tooltip
  if (method !== '5-factor' || Object.keys(factorScores).length === 0) {
    return (
      <Tooltip title="No detailed factor scores available (legacy extraction)">
        {children}
      </Tooltip>
    );
  }

  const factors = [
    {
      key: 'gpt_confidence',
      label: 'GPT Quality',
      icon: <GptIcon fontSize="small" />,
      score: factorScores.gpt_confidence || 0,
      description: 'Base extraction quality'
    },
    {
      key: 'pattern_confidence',
      label: 'Pattern Match',
      icon: <PatternIcon fontSize="small" />,
      score: factorScores.pattern_confidence || 0,
      description: 'ID pattern recognition'
    },
    {
      key: 'structure_score',
      label: 'Structure',
      icon: <StructureIcon fontSize="small" />,
      score: factorScores.structure_score || 0,
      description: 'Field completeness'
    },
    {
      key: 'framework_score',
      label: 'Framework',
      icon: <FrameworkIcon fontSize="small" />,
      score: factorScores.framework_score || 0,
      description: 'TSC/COSO mappings'
    },
    {
      key: 'deviation_score',
      label: 'Deviation',
      icon: <DeviationIcon fontSize="small" />,
      score: factorScores.deviation_score || 0,
      description: 'Flag consistency'
    }
  ];

  const getScoreColor = (score: number) => {
    if (score < 0.5) return 'error';
    if (score < 0.7) return 'warning';
    return 'success';
  };

  const tooltipContent = (
    <Paper 
      elevation={8} 
      sx={{ 
        p: 2, 
        minWidth: 280,
        maxWidth: 320,
        backgroundColor: 'background.paper'
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 'bold' }}>
        5-Factor Confidence Breakdown
      </Typography>
      
      {factors.map((factor) => (
        <Box key={factor.key} sx={{ mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <Box sx={{ color: 'primary.main' }}>
              {factor.icon}
            </Box>
            <Typography variant="caption" sx={{ fontWeight: 500, flex: 1 }}>
              {factor.label}
            </Typography>
            <Typography 
              variant="caption" 
              sx={{ 
                fontWeight: 'bold',
                color: `${getScoreColor(factor.score)}.main`
              }}
            >
              {(factor.score * 100).toFixed(0)}%
            </Typography>
          </Box>
          
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <LinearProgress
              variant="determinate"
              value={factor.score * 100}
              color={getScoreColor(factor.score)}
              sx={{ 
                flex: 1, 
                height: 6, 
                borderRadius: 1,
                backgroundColor: 'action.hover'
              }}
            />
          </Box>
          
          <Typography 
            variant="caption" 
            sx={{ 
              display: 'block', 
              mt: 0.25, 
              fontSize: '0.65rem',
              color: 'text.secondary'
            }}
          >
            {factor.description}
          </Typography>
        </Box>
      ))}

      <Box sx={{ mt: 2, pt: 1.5, borderTop: 1, borderColor: 'divider' }}>
        <Link
          component="button"
          variant="caption"
          onClick={handleClick}
          sx={{ 
            fontSize: '0.75rem',
            fontWeight: 500,
            cursor: 'pointer',
            textDecoration: 'none',
            '&:hover': {
              textDecoration: 'underline'
            }
          }}
        >
          View Details →
        </Link>
      </Box>
    </Paper>
  );

  return (
    <>
      <Box
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
        sx={{ cursor: onClick ? 'pointer' : 'default', display: 'inline-block' }}
      >
        {children}
      </Box>
      
      <Popper
        open={open}
        anchorEl={anchorEl}
        placement="right-start"
        sx={{ zIndex: 1500 }}
        modifiers={[
          {
            name: 'offset',
            options: {
              offset: [0, 8],
            },
          },
        ]}
      >
        {tooltipContent}
      </Popper>
    </>
  );
};

export default ConfidenceTooltip;
