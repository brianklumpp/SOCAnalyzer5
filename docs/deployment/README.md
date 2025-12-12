# Deployment Documentation

This folder contains documentation related to deploying SOCAnalyzer in various environments.

## Quick Links

- [Distribution Quick Reference](DISTRIBUTION_QUICKREF.md) - Fast reference for common deployment tasks
- [Complete Offline Distribution](COMPLETE_OFFLINE_DISTRIBUTION.md) - Offline deployment guide
- [Deployment Checklist v1.0.11](DEPLOYMENT_CHECKLIST_v1.0.11.md) - Step-by-step deployment checklist

## Pre-Deployment

- [Preflight Checklist v1.0.11](PREFLIGHT_CHECKLIST_v1.0.11.md) - Pre-deployment verification steps
- [Pre-deployment Test v1.0.10](PREDEPLOYMENT_TEST_v1.0.10.md) - Testing before deployment

## Distribution

- [Distribution Implementation](DISTRIBUTION_IMPLEMENTATION.md) - How the distribution system works
- [Docker Distribution Summary](DOCKER_DISTRIBUTION_SUMMARY.md) - Docker-based distribution overview
- [Distribution Ready v1.0.9](DISTRIBUTION_READY_v1.0.9.md) - v1.0.9 distribution notes

## Deployment Process

### 1. Pre-Deployment
1. Review [Preflight Checklist](PREFLIGHT_CHECKLIST_v1.0.11.md)
2. Run [Pre-deployment Tests](PREDEPLOYMENT_TEST_v1.0.10.md)
3. Verify system requirements

### 2. Distribution
1. Download distribution package (ZIP file)
2. Verify package integrity
3. Extract to deployment location

### 3. Installation
1. Follow [Deployment Checklist](DEPLOYMENT_CHECKLIST_v1.0.11.md)
2. Run `IMPORT.ps1` script
3. Verify services start correctly

### 4. Post-Deployment
1. Run `test_deployment.ps1`
2. Verify application access
3. Check all services are healthy

## Distribution Package Contents

Each distribution package includes:
- Pre-built Docker images (.tar files)
- docker-compose.yml (production config)
- Environment template (.env.dist)
- Import/Export scripts
- Backup/Restore utilities
- Test scripts
- Documentation

## Supported Deployment Scenarios

- **Online Deployment**: Direct internet access for Docker Hub images
- **Offline Deployment**: Pre-packaged images for air-gapped environments
- **Fresh Installation**: New deployment on clean system
- **Upgrade**: Upgrading from previous version

## Common Issues

See [../troubleshooting/](../troubleshooting/) folder for:
- Common deployment errors
- Fix procedures
- Troubleshooting guides

## Related Documentation

- [../ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture overview
- [../QUICKSTART.md](../QUICKSTART.md) - Quick start guide
- [../DEPLOYMENT_CHECKLIST.md](../DEPLOYMENT_CHECKLIST.md) - Main deployment checklist
