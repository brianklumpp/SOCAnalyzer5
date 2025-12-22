/**
 * DEV-only health check to verify Vite proxy configuration
 * 
 * This utility validates that all critical backend routes are properly
 * proxied by the Vite dev server. Only runs in development mode.
 * 
 * @see frontend/vite.config.ts - Proxy configuration
 * @see backend/app/main.py - Router registrations
 */

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
  // Skip health check in production builds
  if (import.meta.env.PROD) {
    return { healthy: true, results: [] };
  }

  console.log('🔍 Running DEV proxy health check...');

  const results = await Promise.all(
    BACKEND_ROUTES.map(async (route): Promise<HealthCheckResult> => {
      try {
        const response = await fetch(route);
        
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
