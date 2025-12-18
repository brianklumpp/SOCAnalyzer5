/**
 * Solidigm Theme Configuration
 * 
 * Brand colors and Material-UI theme customization for SOC Analyzer
 */

import { createTheme, ThemeOptions, PaletteMode } from '@mui/material/styles';

// Solidigm Brand Colors
export const solidigmColors = {
  purple: '#4F00B5',      // Primary brand color
  darkBlue: '#00083F',    // Secondary brand color
  teal: '#97F2E9',        // Accent color
  orange: '#FFA42C',      // Warning/highlight color
  // Additional neutral colors
  darkGray: '#2C2C2C',
  lightGray: '#F5F5F5',
  mediumGray: '#757575',
};

// Create theme configuration for light/dark modes
export const createSolidigmTheme = (mode: PaletteMode) => {
  const isDark = mode === 'dark';
  
  const themeOptions: ThemeOptions = {
    palette: {
      mode,
      primary: {
        main: solidigmColors.purple,
        light: isDark ? '#6B2DC4' : '#7030D3',
        dark: isDark ? '#3A0089' : '#3A0089',
        contrastText: '#FFFFFF',
      },
      secondary: {
        main: solidigmColors.darkBlue,
        light: isDark ? '#1A2A5F' : '#2A3A6F',
        dark: isDark ? '#000525' : '#000525',
        contrastText: '#FFFFFF',
      },
      error: {
        main: '#D32F2F',
      },
      warning: {
        main: solidigmColors.orange,
      },
      info: {
        main: isDark ? solidigmColors.teal : '#0288D1',
      },
      success: {
        main: '#388E3C',
      },
      background: {
        default: isDark ? '#121212' : '#FAFAFA',
        paper: isDark ? '#1E1E1E' : '#FFFFFF',
      },
      text: {
        primary: isDark ? 'rgba(255, 255, 255, 0.87)' : 'rgba(0, 0, 0, 0.87)',
        secondary: isDark ? 'rgba(255, 255, 255, 0.60)' : 'rgba(0, 0, 0, 0.60)',
      },
    },
    typography: {
      fontFamily: [
        '-apple-system',
        'BlinkMacSystemFont',
        '"Segoe UI"',
        'Roboto',
        '"Helvetica Neue"',
        'Arial',
        'sans-serif',
      ].join(','),
      h1: {
        fontSize: '2.5rem',
        fontWeight: 600,
      },
      h2: {
        fontSize: '2rem',
        fontWeight: 600,
      },
      h3: {
        fontSize: '1.75rem',
        fontWeight: 500,
      },
      h4: {
        fontSize: '1.5rem',
        fontWeight: 500,
      },
      h5: {
        fontSize: '1.25rem',
        fontWeight: 500,
      },
      h6: {
        fontSize: '1rem',
        fontWeight: 500,
      },
      body1: {
        fontSize: '1rem',
      },
      body2: {
        fontSize: '0.875rem',
      },
    },
    shape: {
      borderRadius: 8,
    },
    components: {
      MuiButton: {
        styleOverrides: {
          root: {
            textTransform: 'none',
            fontWeight: 500,
            borderRadius: 8,
            padding: '8px 16px',
          },
          contained: {
            boxShadow: 'none',
            '&:hover': {
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
            },
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            boxShadow: isDark
              ? '0 2px 8px rgba(0, 0, 0, 0.3)'
              : '0 2px 8px rgba(0, 0, 0, 0.08)',
            transition: 'all 0.3s ease-in-out',
            '&:hover': {
              boxShadow: isDark
                ? '0 8px 24px rgba(0, 0, 0, 0.4)'
                : '0 8px 24px rgba(0, 0, 0, 0.12)',
              transform: 'scale(1.02)',
            },
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: 6,
            fontWeight: 500,
          },
        },
      },
      MuiTextField: {
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-root': {
              borderRadius: 8,
            },
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            borderRadius: 8,
          },
          elevation1: {
            boxShadow: isDark
              ? '0 1px 3px rgba(0, 0, 0, 0.3)'
              : '0 1px 3px rgba(0, 0, 0, 0.08)',
          },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: {
            boxShadow: isDark
              ? '0 2px 8px rgba(0, 0, 0, 0.3)'
              : '0 2px 8px rgba(0, 0, 0, 0.08)',
          },
        },
      },
      MuiLinearProgress: {
        styleOverrides: {
          root: {
            borderRadius: 4,
            height: 8,
          },
        },
      },
    },
  };

  return createTheme(themeOptions);
};

// Export pre-configured themes
export const lightTheme = createSolidigmTheme('light');
export const darkTheme = createSolidigmTheme('dark');
