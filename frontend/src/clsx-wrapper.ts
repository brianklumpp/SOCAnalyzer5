// Wrapper to ensure clsx is available for MUI's CommonJS require()
import clsx from 'clsx';

// Export as both default and named for maximum compatibility
export { clsx };
export default clsx;

// Also attach to window for runtime fallback
if (typeof window !== 'undefined') {
  (window as any).clsx = clsx;
}
