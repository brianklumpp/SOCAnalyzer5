# DEV vs PROD Routing Architecture

## Overview

SOCAnalyzer uses different routing strategies for development (DEV) and production (PROD) environments. Understanding these differences is critical for debugging routing issues and maintaining parity between environments.

## Architecture Comparison

### DEV Environment (Docker + Vite Dev Server)

```
Browser (localhost:3000)
  ↓
Vite Dev Server (frontend container, port 3000)
  ├─ Static assets: Served by Vite with HMR
  ├─ Frontend routes: Handled by React Router
  └─ Backend API routes: Proxied to backend container
      ↓
Backend Container (FastAPI, port 8000)
```

**Key Characteristics**:
- **Hot Module Replacement (HMR)**: Code changes reflect instantly without full reload
- **Source maps**: Full debugging support with original TypeScript source
- **Selective proxy**: Only routes matching regex pattern are forwarded to backend
- **Bind mounts**: Source code mounted directly from host filesystem
- **Configuration**: `frontend/vite.config.ts` (server.proxy section)

**Vite Proxy Pattern**:
```typescript
proxy: {
  '^/(analyze|report|controls|cuecs|suborgs|deviations|executive_summary|baseline|config|auth|users|grace|history|settings|framework_criteria|pdf|docker|test|validate|help|diag)': {
    target: 'http://backend:8000',
    changeOrigin: true,
  },
  '/ws': {
    target: 'ws://backend:8000',
    ws: true,
  },
}
```

### PROD Environment (Docker + nginx)

```
Browser (10.74.214.9:3000)
  ↓
nginx (frontend container, port 3000)
  ├─ Static assets: Served from /app/build
  ├─ Frontend routes: Handled by React Router (SPA fallback)
  └─ Backend API routes: Reverse proxied to backend container
      ↓
Backend Container (FastAPI, port 8000)
```

**Key Characteristics**:
- **Pre-built static files**: Frontend compiled with `vite build`, served as optimized bundles
- **No source maps**: Minified, production-optimized code
- **Comprehensive reverse proxy**: nginx location blocks catch all backend routes
- **Immutable volumes**: Build artifacts copied into container during build
- **Configuration**: `docker-compose.prod.yml` (nginx config section)

**nginx Proxy Pattern**:
```nginx
location ~ ^/(analyze|report|controls|cuecs|suborgs|deviations|executive_summary|baseline|config|auth|users|grace|history|settings|framework_criteria|pdf|docker|test|validate|help|diag|ws) {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# WebSocket support
location /ws {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}

# SPA fallback for frontend routes
location / {
    root /app/build;
    try_files $uri $uri/ /index.html;
}
```

## Common Issues

### Issue: Route works in PROD but returns 404 in DEV

**Symptoms**:
- Browser console shows "Failed to load resource: the server responded with a status of 404"
- Network tab shows HTML response (Vite's 404 page), not JSON
- Same endpoint works perfectly in PROD

**Root Cause**:
Route not included in Vite proxy pattern. When Vite receives a request for an unknown route, it tries to serve it as a static file, resulting in its own 404 page.

**Example**:
```
Request: POST /config/max-concurrent-scans
Vite proxy: Only covers /api, /auth, /ws
Result: Vite returns HTML 404 (not proxied to backend)
```

**Solution**:
1. Identify the missing route prefix (e.g., `/config`)
2. Add it to the Vite proxy regex pattern in `frontend/vite.config.ts`
3. Restart the frontend container: `docker-compose restart frontend`

### Issue: GRaCe works in PROD but fails in DEV

**Symptoms**:
- "Failed to get response from GRaCe" error
- Network tab shows 404 for `/grace/{scan_id}/message`

**Root Cause**:
`/grace` prefix not in Vite proxy pattern (if using old config with only `/api`, `/auth`, `/ws`).

**Solution**:
Already fixed in current vite.config.ts. The comprehensive regex pattern includes `grace`.

### Issue: Settings page works in PROD but not DEV

**Symptoms**:
- Cannot change queue settings
- POST `/config/max-concurrent-scans` returns 404
- Network tab shows HTML response

**Root Cause**:
`/config` prefix not in Vite proxy pattern.

**Solution**:
Already fixed in current vite.config.ts. The comprehensive regex pattern includes `config`.

## Health Check Utility

To automatically detect proxy configuration issues in DEV, the frontend runs a health check on startup:

**File**: `frontend/src/utils/devHealthCheck.ts`

**What it does**:
1. Only runs in development mode (`import.meta.env.DEV`)
2. Tests 7 critical backend routes
3. Verifies routes are proxied (backend responds) vs not proxied (Vite 404)
4. Outputs results to browser console as a table

**Output Example**:
```
🔍 Running DEV proxy health check...
📊 Health check results:
┌─────────┬────────────────────────────┬──────────────────────────────────┐
│ (index) │ route                      │ status                           │
├─────────┼────────────────────────────┼──────────────────────────────────┤
│ 0       │ '/analyze/queue'           │ '✅ Proxied (404 from backend)'  │
│ 1       │ '/report/1'                │ '✅ Proxied (404 from backend)'  │
│ 2       │ '/config/runtime'          │ '✅ Proxied (200)'               │
│ 3       │ '/auth/me'                 │ '✅ Proxied (401 auth required)' │
│ 4       │ '/grace/1/history'         │ '✅ Proxied (404 from backend)'  │
│ 5       │ '/framework_criteria'      │ '✅ Proxied (200)'               │
│ 6       │ '/settings'                │ '✅ Proxied (404 from backend)'  │
└─────────┴────────────────────────────┴──────────────────────────────────┘
✅ All routes properly proxied to backend
```

**If proxy is broken**:
```
⚠️ Some routes are not properly proxied! Check vite.config.ts
┌─────────┬────────────────────────────┬───────────────────────────────────────┐
│ (index) │ route                      │ status                                │
├─────────┼────────────────────────────┼───────────────────────────────────────┤
│ 2       │ '/config/runtime'          │ '❌ Not Proxied (Vite 404)'           │
│         │                            │ error: 'Route not matched by pattern' │
└─────────┴────────────────────────────┴───────────────────────────────────────┘
```

## Maintenance Procedures

### Adding a New Backend Router

When adding a new FastAPI router with a new prefix:

1. **Register router in backend** (`backend/app/main.py`):
   ```python
   from app.routers import new_router
   app.include_router(new_router.router, tags=["new_feature"])
   ```

2. **Update Vite proxy pattern** (`frontend/vite.config.ts`):
   ```typescript
   '^/(analyze|report|...|new_feature)': {
     target: 'http://backend:8000',
     changeOrigin: true,
   },
   ```

3. **Update nginx config** (`docker-compose.prod.yml`):
   ```nginx
   location ~ ^/(analyze|report|...|new_feature) {
       proxy_pass http://backend:8000;
   }
   ```

4. **Restart DEV frontend**: `docker-compose restart frontend`

5. **Rebuild PROD frontend**: `docker-compose -f docker-compose.prod.yml up -d --build frontend`

### Verifying Routing Parity

To ensure DEV and PROD routing behavior matches:

1. **Check health check output** in DEV browser console (F12)
2. **Test critical flows** in both environments:
   - Settings page (queue configuration)
   - GRaCe chat
   - Report generation
   - Scan queue management
3. **Compare network tabs**: Backend routes should return same status codes (200, 401, 404) in both environments
4. **Monitor backend logs**: `docker-compose logs backend --tail=50 --follow`

## Troubleshooting Guide

### Route returns 404 in DEV

1. Open browser console (F12) and check health check results
2. Check if route prefix is in Vite proxy pattern (`frontend/vite.config.ts`)
3. If missing, add to regex pattern and restart: `docker-compose restart frontend`
4. Clear browser cache (Ctrl+Shift+Delete) and reload

### Route returns HTML instead of JSON

- **Symptom**: Network tab shows HTML response with Vite's 404 page
- **Cause**: Route not proxied, Vite serving its own 404
- **Fix**: Add route prefix to Vite proxy pattern

### Changes to vite.config.ts not taking effect

- **Cause**: Frontend container needs restart to reload Vite config
- **Fix**: `docker-compose restart frontend` (wait 10-15 seconds for Vite to start)
- **Verify**: Check `docker-compose logs frontend --tail=20` for "VITE ready" message

### Backend responds but frontend shows error

- **Cause**: Frontend code issue, not routing
- **Debug**: Check browser console for JavaScript errors
- **Verify**: Use curl to test backend directly:
  ```bash
  docker exec backend curl http://localhost:8000/config/runtime
  ```

## Best Practices

1. **Keep proxy patterns in sync**: When adding a backend router, update both Vite config (DEV) and nginx config (PROD)
2. **Test in DEV first**: Always verify routing works in DEV before deploying to PROD
3. **Monitor health checks**: Review browser console on DEV startup to catch proxy issues early
4. **Document new routes**: Update this file when adding significant new route prefixes
5. **Use comprehensive patterns**: Prefer inclusive regex patterns over granular individual routes for maintainability

## Configuration Files Reference

- **DEV Proxy**: `frontend/vite.config.ts` (server.proxy section)
- **PROD Proxy**: `docker-compose.prod.yml` (nginx config section)
- **Backend Routers**: `backend/app/main.py` (app.include_router calls)
- **Health Check**: `frontend/src/utils/devHealthCheck.ts`
- **Router Definitions**: `backend/app/routers/*.py`

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Overall system architecture
- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) - PROD deployment steps
- [Vite Proxy Documentation](https://vitejs.dev/config/server-options.html#server-proxy)
- [nginx Reverse Proxy Guide](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/)
