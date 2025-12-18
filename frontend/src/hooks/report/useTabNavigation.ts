import { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

export function useTabNavigation(initialTab: number = 0) {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabScrollPositions = useRef<{[key: number]: number}>({});
  
  // Tab state: initialize from URL param or localStorage, default to initialTab
  const tabFromUrl = searchParams.get('tab');
  const tabFromStorage = localStorage.getItem('socanalyzer_active_tab');
  const startTab = tabFromUrl ? parseInt(tabFromUrl, 10) : (tabFromStorage ? parseInt(tabFromStorage, 10) : initialTab);
  const [activeTab, setActiveTab] = useState<number>(startTab);
  
  // Handle tab change with URL and localStorage persistence
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
    localStorage.setItem('socanalyzer_active_tab', newValue.toString());
    setSearchParams({ tab: newValue.toString() });
  };
  
  // Keyboard navigation for tabs (Ctrl+PageUp/PageDown)
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey) {
        if (event.key === 'PageUp') {
          event.preventDefault();
          setActiveTab(prev => (prev > 0 ? prev - 1 : 5));
        } else if (event.key === 'PageDown') {
          event.preventDefault();
          setActiveTab(prev => (prev < 5 ? prev + 1 : 0));
        }
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);
  
  return {
    activeTab,
    setActiveTab,
    handleTabChange,
    tabScrollPositions,
    searchParams,
    setSearchParams
  };
}
