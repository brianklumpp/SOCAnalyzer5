/**
 * SplitViewContext
 * 
 * Manages split view state across the application with localStorage persistence.
 * Tracks split view enabled/disabled state and orientation per scan and tab.
 */

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';

interface SplitViewState {
  enabled: boolean;
  orientation: 'horizontal' | 'vertical';
}

interface SplitViewContextType {
  getSplitViewState: (scanId: number, tabName: string) => SplitViewState;
  setSplitViewEnabled: (scanId: number, tabName: string, enabled: boolean) => void;
  setSplitViewOrientation: (scanId: number, tabName: string, orientation: 'horizontal' | 'vertical') => void;
  toggleSplitView: (scanId: number, tabName: string) => void;
  toggleOrientation: (scanId: number, tabName: string) => void;
}

const SplitViewContext = createContext<SplitViewContextType | undefined>(undefined);

export const useSplitView = () => {
  const context = useContext(SplitViewContext);
  if (!context) {
    throw new Error('useSplitView must be used within SplitViewProvider');
  }
  return context;
};

interface SplitViewProviderProps {
  children: React.ReactNode;
}

export const SplitViewProvider: React.FC<SplitViewProviderProps> = ({ children }) => {
  // State to trigger re-renders when split view changes
  const [, forceUpdate] = useState({});
  // In-memory state cache - using useRef to avoid setState during render
  const stateCacheRef = React.useRef<Map<string, SplitViewState>>(new Map());

  // Generate storage key
  const getStorageKey = (scanId: number, tabName: string): string => {
    return `splitView_${scanId}_${tabName}`;
  };

  // Load state from localStorage
  const loadState = useCallback((scanId: number, tabName: string): SplitViewState => {
    const key = getStorageKey(scanId, tabName);
    
    // Check cache first
    if (stateCacheRef.current.has(key)) {
      return stateCacheRef.current.get(key)!;
    }

    // Load from localStorage
    const enabledKey = `${key}_enabled`;
    const orientationKey = `${key}_orientation`;
    
    const enabled = localStorage.getItem(enabledKey) === 'true';
    const orientation = (localStorage.getItem(orientationKey) as 'horizontal' | 'vertical') || 'horizontal';

    const state: SplitViewState = { enabled, orientation };
    
    // Cache it (using ref, not setState)
    stateCacheRef.current.set(key, state);
    
    return state;
  }, []);

  // Save state to localStorage and cache
  const saveState = useCallback((scanId: number, tabName: string, state: SplitViewState) => {
    const key = getStorageKey(scanId, tabName);
    
    // Save to localStorage
    localStorage.setItem(`${key}_enabled`, state.enabled.toString());
    localStorage.setItem(`${key}_orientation`, state.orientation);
    
    // Update cache (using ref, not setState)
    stateCacheRef.current.set(key, state);
    
    // Force re-render to propagate changes
    forceUpdate({});
  }, []);

  const getSplitViewState = useCallback((scanId: number, tabName: string): SplitViewState => {
    return loadState(scanId, tabName);
  }, [loadState]);

  const setSplitViewEnabled = useCallback((scanId: number, tabName: string, enabled: boolean) => {
    const currentState = loadState(scanId, tabName);
    const newState = { ...currentState, enabled };
    saveState(scanId, tabName, newState);
  }, [loadState, saveState]);

  const setSplitViewOrientation = useCallback((scanId: number, tabName: string, orientation: 'horizontal' | 'vertical') => {
    const currentState = loadState(scanId, tabName);
    const newState = { ...currentState, orientation };
    saveState(scanId, tabName, newState);
  }, [loadState, saveState]);

  const toggleSplitView = useCallback((scanId: number, tabName: string) => {
    const currentState = loadState(scanId, tabName);
    const newState = { ...currentState, enabled: !currentState.enabled };
    saveState(scanId, tabName, newState);
  }, [loadState, saveState]);

  const toggleOrientation = useCallback((scanId: number, tabName: string) => {
    const currentState = loadState(scanId, tabName);
    const newOrientation = currentState.orientation === 'horizontal' ? 'vertical' : 'horizontal';
    const newState = { ...currentState, orientation: newOrientation };
    saveState(scanId, tabName, newState);
  }, [loadState, saveState]);

  const value: SplitViewContextType = {
    getSplitViewState,
    setSplitViewEnabled,
    setSplitViewOrientation,
    toggleSplitView,
    toggleOrientation,
  };

  return (
    <SplitViewContext.Provider value={value}>
      {children}
    </SplitViewContext.Provider>
  );
};
