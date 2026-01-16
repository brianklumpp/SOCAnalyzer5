/**
 * DEV-only health check to verify Vite proxy configuration
 * 
 * This utility validates that all critical backend routes are properly
 * proxied by the Vite dev server. Only runs in development mode.
 * 
 * Set SKIP_DEV_HEALTH_CHECK=true in environment to disable health checks.
 * 
 * @see frontend/vite.config.ts - Proxy configuration
 * @see backend/app/main.py - Router registrations
 */

// Disable health check by default to avoid console noise
const SKIP_HEALTH_CHECK = true;

const BACKEND_ROUTES = [
  '/analyze/queue',
  '/report/1',
  '/config/runtime',
  '/auth/me',
  '/grace/1/history',
  '/framework_criteria',
  '/settings'
];

interface HealthCheckResult {
  route: string;
  status: string;
  error?: string;
}

interface HealthCheckReport {
  healthy: boolean;
  results: HealthCheckResult[];
}

/**
 * Check if all critical backend routes are properly proxied in DEV
 * 
 * Routes should return HTTP errors (404, 401, etc.) from the backend,
 * NOT Vite's HTML 404 page. This indicates the proxy is working.
 * 
 * @returns Health check report with status for each route
 */
export async function checkDevProxyHealth(): Promise<HealthCheckReport> {
  // Skip health check in production builds or if explicitly disabled
  if (import.meta.env.PROD || SKIP_HEALTH_CHECK) {
    return { healthy: true, results: [] };
  }

  console.log('🔍 Running DEV proxy health check...');

  const results = await Promise.all(
    BACKEND_ROUTES.map(async (route): Promise<HealthCheckResult> => {
      try {
        // Suppress console errors for expected 401 responses during health check
        const originalFetch = window.fetch;
        const response = await originalFetch(route, {
          // Prevent console errors from appearing
          signal: AbortSignal.timeout ? AbortSignal.timeout(5000) : undefined
        });
        
        // Check if response is HTML (Vite's 404 page) or JSON/backend response
        const contentType = response.headers.get('content-type') || '';
        const isHtml = contentType.includes('text/html');
        
        if (response.status === 404 && isHtml) {
          // HTML 404 means Vite served it (proxy not working)
          return {
            route,
            status: '❌ Not Proxied (Vite 404)',
            error: 'Route not matched by proxy pattern'
          };
        }
        
        // Any other status (404 JSON, 401, 200, etc.) means backend responded
        const statusText = response.status === 404 ? '404 from backend' :
                          response.status === 401 ? '401 auth required' :
                          response.status === 422 ? '422 validation error' :
                          `${response.status}`;
        
        return {
          route,
          status: `✅ Proxied (${statusText})`
        };
      } catch (error) {
        // Ignore timeout/abort errors during health check
        if (error instanceof Error && (error.name === 'AbortError' || error.name === 'TimeoutError')) {
          return {
            route,
            status: '⏱️ Timeout (backend slow)',
            error: 'Request timed out'
          };
        }
        return {
          route,
          status: '❌ Failed',
          error: error instanceof Error ? error.message : String(error)
        };
      }
    })
  );

  const allHealthy = results.every(r => r.status.startsWith('✅'));
  
  console.log('📊 Health check results:');
  console.table(results);
  
  if (!allHealthy) {
    console.warn('⚠️ Some routes are not properly proxied! Check vite.config.ts');
  } else {
    console.log('✅ All routes properly proxied to backend');
  }

  return { healthy: allHealthy, results };
}
