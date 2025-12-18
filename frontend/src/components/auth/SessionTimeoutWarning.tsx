import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  LinearProgress,
} from '@mui/material';
import { useAuth } from '../../contexts/AuthContext';

interface SessionTimeoutWarningProps {
  warningMinutes?: number; // Show warning this many minutes before expiration
  checkIntervalSeconds?: number; // Check token expiration every X seconds
}

const SessionTimeoutWarning: React.FC<SessionTimeoutWarningProps> = ({
  warningMinutes = 5,
  checkIntervalSeconds = 30,
}) => {
  const { accessToken, refreshAccessToken, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [secondsRemaining, setSecondsRemaining] = useState<number>(0);

  useEffect(() => {
    if (!accessToken) {
      setOpen(false);
      return;
    }

    const checkExpiration = () => {
      try {
        // Decode JWT token to get expiration
        const payload = JSON.parse(atob(accessToken.split('.')[1]));
        const expirationTime = payload.exp * 1000; // Convert to milliseconds
        const currentTime = Date.now();
        const timeRemaining = expirationTime - currentTime;
        const secondsLeft = Math.floor(timeRemaining / 1000);
        
        // Show warning if less than warningMinutes remaining
        const warningThreshold = warningMinutes * 60;
        
        if (secondsLeft <= warningThreshold && secondsLeft > 0) {
          setSecondsRemaining(secondsLeft);
          setOpen(true);
        } else if (secondsLeft <= 0) {
          // Token expired
          setOpen(false);
        } else {
          setOpen(false);
        }
      } catch (error) {
        console.error('Failed to parse token:', error);
      }
    };

    // Check immediately
    checkExpiration();

    // Set up interval to check periodically
    const interval = setInterval(checkExpiration, checkIntervalSeconds * 1000);

    return () => clearInterval(interval);
  }, [accessToken, warningMinutes, checkIntervalSeconds]);

  // Update countdown every second when dialog is open
  useEffect(() => {
    if (!open) return;

    const countdown = setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev <= 1) {
          setOpen(false);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(countdown);
  }, [open]);

  const handleExtendSession = async () => {
    try {
      await refreshAccessToken();
      setOpen(false);
    } catch (error) {
      console.error('Failed to extend session:', error);
      // Let the auth context handle the logout
    }
  };

  const handleLogout = async () => {
    setOpen(false);
    await logout();
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const progress = (secondsRemaining / (warningMinutes * 60)) * 100;

  return (
    <Dialog
      open={open}
      onClose={() => {}} // Prevent closing by clicking outside
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>Session Expiring Soon</DialogTitle>
      <DialogContent>
        <Box sx={{ mb: 2 }}>
          <Typography variant="body1" gutterBottom>
            Your session will expire in:
          </Typography>
          <Typography variant="h4" color="error" sx={{ my: 2, textAlign: 'center' }}>
            {formatTime(secondsRemaining)}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={progress}
            sx={{ height: 8, borderRadius: 1 }}
          />
        </Box>
        <Typography variant="body2" color="text.secondary">
          Would you like to extend your session?
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleLogout} color="error">
          Logout
        </Button>
        <Button onClick={handleExtendSession} variant="contained" autoFocus>
          Extend Session
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default SessionTimeoutWarning;
