export const API_URL = "/report/";
export const HISTORY_URL = "/history";
export const FRAMEWORK_CRITERIA_URL = "/framework_criteria";
// Modern router path: /report/{scan_id}/executive_summary
export const EXEC_SUMMARY_PATH = "executive_summary";

// Note: These values should match backend's HIGH_CONFIDENCE_THRESHOLD config
// The backend is the source of truth - fetched via /config/runtime endpoint
export const CONFIDENCE_THRESHOLD = 0.75;
export const CONFIDENCE_THRESHOLD_PERCENT = 75;
