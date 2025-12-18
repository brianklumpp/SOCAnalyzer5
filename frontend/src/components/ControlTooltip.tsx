import React from 'react';
import { Box, Typography, Paper, Popper, Link } from '@mui/material';

interface ControlTooltipProps {
  control: any;
  children: React.ReactElement;
  onClick?: () => void;
}

const ControlTooltip: React.FC<ControlTooltipProps> = ({ control, children, onClick }) => {
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);

  const handleMouseEnter = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMouseLeave = () => {
    setAnchorEl(null);
  };

  const handleClick = () => {
    setAnchorEl(null);
    if (onClick) onClick();
  };

  const truncate = (text: any, maxLength: number = 150): string => {
    if (!text) return 'N/A';
    const str = Array.isArray(text) ? text.join('; ') : String(text);
    return str.length > maxLength ? str.substring(0, maxLength) + '...' : str;
  };

  const tooltipContent = (
    <Paper elevation={8} sx={{ p: 2, minWidth: 280, maxWidth: 400 }}>
      <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 'bold' }}>
        Control Preview
      </Typography>
      
      <Box sx={{ mb: 1 }}>
        <Typography variant="caption" sx={{ fontWeight: 500, color: 'text.secondary' }}>
          Description:
        </Typography>
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          {truncate(control.control_desc)}
        </Typography>
      </Box>

      {control.control_test && (
        <Box sx={{ mb: 1 }}>
          <Typography variant="caption" sx={{ fontWeight: 500, color: 'text.secondary' }}>
            Test:
          </Typography>
          <Typography variant="body2" sx={{ mt: 0.5 }}>
            {truncate(control.control_test)}
          </Typography>
        </Box>
      )}

      {control.has_deviation && (
        <Box sx={{ mb: 1 }}>
          <Typography variant="caption" sx={{ fontWeight: 500, color: 'error.main' }}>
            ⚠ Has Deviation
          </Typography>
        </Box>
      )}

      <Box sx={{ mt: 2, pt: 1.5, borderTop: 1, borderColor: 'divider' }}>
        <Link
          component="button"
          variant="caption"
          onClick={handleClick}
          sx={{ fontSize: '0.75rem', fontWeight: 500, cursor: 'pointer' }}
        >
          View Full Details →
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
        modifiers={[{ name: 'offset', options: { offset: [0, 8] } }]}
      >
        {tooltipContent}
      </Popper>
    </>
  );
};

export default ControlTooltip;
