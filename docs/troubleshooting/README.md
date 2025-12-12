# Troubleshooting Documentation

This folder contains documentation for fixing common issues and bugs in SOCAnalyzer.

## Available Guides

- [BUGFIX_SUMMARY.md](BUGFIX_SUMMARY.md) - Summary of recent bug fixes
- [CRITICAL_FIX_v1.0.10.md](CRITICAL_FIX_v1.0.10.md) - Critical fixes in v1.0.10
- [MANAGER_UPDATE_FIX.md](MANAGER_UPDATE_FIX.md) - Manager executable update fix
- [TESTER-FIX-REDIS-CONNECTION.md](TESTER-FIX-REDIS-CONNECTION.md) - Redis connection issues for testers

## Common Issues

### Database Issues
- **Column does not exist errors**: See [CRITICAL_FIX_v1.0.10.md](CRITICAL_FIX_v1.0.10.md)
- **Migration failures**: Check migration logs with `docker compose logs backend | grep migration`
- **Connection refused**: Verify PostgreSQL is running with `docker compose ps postgres`

### Redis Connection Issues
- **Connection refused**: See [TESTER-FIX-REDIS-CONNECTION.md](TESTER-FIX-REDIS-CONNECTION.md)
- **DNS resolution**: Check DNS cache service is running
- **Port conflicts**: Verify port 6379 is not in use

### Certificate Issues
- **SSL/TLS errors**: Check certificate bundle in `certs/` folder
- **Corporate CA issues**: May need to import custom CA certificates

### Manager Executable Issues
- **Update failures**: See [MANAGER_UPDATE_FIX.md](MANAGER_UPDATE_FIX.md)
- **Version mismatches**: Verify manager version matches backend version

## Diagnostic Steps

### 1. Check Service Status
```powershell
docker compose ps
```

All services should show "Up" status.

### 2. View Logs
```powershell
# All services
docker compose logs

# Specific service
docker compose logs backend
docker compose logs postgres
docker compose logs redis
```

### 3. Test Connectivity
```powershell
# Test deployment script
.\test_deployment.ps1

# Manual health checks
curl http://localhost:5001/health
curl http://localhost:8000/health
```

### 4. Check Database
```powershell
# Connect to database
docker compose exec postgres psql -U soc2_analyzer -d soc2analyzer

# Check migration version
SELECT version_num FROM alembic_version;
```

## Getting Help

If issues persist:

1. **Check recent fixes**: Review [BUGFIX_SUMMARY.md](BUGFIX_SUMMARY.md)
2. **Check version-specific issues**: See release notes in [../releases/](../releases/)
3. **Collect diagnostic info**:
   ```powershell
   docker compose logs > logs.txt
   docker compose ps > services.txt
   ```
4. **Review deployment docs**: See [../deployment/](../deployment/)

## Related Documentation

- [../ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [../deployment/](../deployment/) - Deployment guides
- [../releases/](../releases/) - Release notes with fixes
- [../V1_0_12_CERTIFICATE_AND_SCHEMA_FIX.md](../V1_0_12_CERTIFICATE_AND_SCHEMA_FIX.md) - Certificate fix details

## Prevention

To avoid common issues:

- Always use latest distribution package
- Follow deployment checklists
- Run pre-deployment tests
- Backup before upgrades
- Review release notes before updating
