# SOC Analyzer Documentation

Welcome to the SOC Analyzer documentation! This folder contains all technical documentation, implementation guides, and reference materials.

## 🚀 Quick Start

**New to SOC Analyzer?**
1. Read [QUICKSTART.md](QUICKSTART.md) for a quick introduction
2. Check [DOCKER_SETUP_REFERENCE.md](DOCKER_SETUP_REFERENCE.md) for development setup

**Looking for something specific?**
- See [INDEX.md](INDEX.md) for a complete categorized list of all documentation

## 📚 Documentation Structure

```
docs/
├── INDEX.md                    # Complete documentation index
├── DOCKER_SETUP_REFERENCE.md   # ⚠️ CRITICAL - Docker development guide
├── ARCHITECTURE.md             # System architecture overview
├── MANAGEMENT_RESPONSE_FEATURE.md  # 🆕 Latest feature (Dec 2025)
│
├── help/                       # User-facing help system
│   ├── whats-new.md           # Latest updates and features
│   ├── getting-started/       # Getting started guides
│   ├── features/              # Feature documentation
│   ├── workflows/             # Workflow guides
│   └── troubleshooting/       # User troubleshooting
│
├── deployment/                # Deployment documentation
├── troubleshooting/           # Developer troubleshooting
└── releases/                  # Release notes
```

## 🎯 Find Documentation By Purpose

### I want to...

**Develop locally**
- [DOCKER_SETUP_REFERENCE.md](DOCKER_SETUP_REFERENCE.md) - **START HERE**
- [ARCHITECTURE.md](ARCHITECTURE.md) - System overview
- [DIRECT_EXECUTION_GUIDE.md](DIRECT_EXECUTION_GUIDE.md) - Run without Docker

**Understand features**
- [MANAGEMENT_RESPONSE_FEATURE.md](MANAGEMENT_RESPONSE_FEATURE.md) - Management response extraction (NEW)
- [CONTROL_EXTRACTOR_V4_SUMMARY.md](CONTROL_EXTRACTOR_V4_SUMMARY.md) - Control extraction V4
- [5_FACTOR_CONFIDENCE_IMPLEMENTATION.md](5_FACTOR_CONFIDENCE_IMPLEMENTATION.md) - Confidence scoring
- [AUTHENTICATION_COMPLETE.md](AUTHENTICATION_COMPLETE.md) - Windows SSO auth

**Deploy to production**
- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) - Deployment procedures
- [deployment/](deployment/) - Deployment guides

**Troubleshoot issues**
- [troubleshooting/](troubleshooting/) - Troubleshooting guides
- [DOCKER_SETUP_REFERENCE.md](DOCKER_SETUP_REFERENCE.md) - Docker troubleshooting section

**Configure the system**
- [GPT_MODEL_CONFIG.md](GPT_MODEL_CONFIG.md) - GPT configuration
- [DNS_FALLBACK_SETUP.md](DNS_FALLBACK_SETUP.md) - DNS fallback

**Understand the pipeline**
- [EXECUTION_FLOW_DIAGRAM.md](EXECUTION_FLOW_DIAGRAM.md) - Pipeline flow
- [DATA_PIPELINE_CONSISTENCY.md](DATA_PIPELINE_CONSISTENCY.md) - Data flow
- [INDIVIDUAL_EXTRACTORS.md](INDIVIDUAL_EXTRACTORS.md) - Extractor details

## 🆕 Latest Updates (December 2025)

### New Features
- **Management Response Extraction** - Automatically extract and display management responses to deviations
- **CUEC Confidence Adjustments** - Refined confidence scoring weights
- **Deviation Tab Auth Fix** - Fixed 401 errors with proper authentication

See [help/whats-new.md](help/whats-new.md) for complete release notes.

## 📖 Documentation Types

### User Documentation
Located in `help/` - Designed for end users of the application
- Getting started guides
- Feature walkthroughs
- Workflow tutorials
- User troubleshooting

### Developer Documentation
Root level docs - Technical implementation details
- Architecture and design
- Feature implementation guides
- API documentation
- Developer troubleshooting

### Historical Documentation
Status updates and implementation notes from development
- Week progress documents (WEEK2_COMPLETE.md, etc.)
- Phase completion notes
- Implementation summaries
- Consider archiving older status docs

## 🔍 Search Tips

**Find by keyword:**
```bash
# Search all markdown files
grep -r "keyword" docs/ --include="*.md"

# Search specific topic
grep -r "authentication" docs/ --include="*.md"
```

**Browse by category:**
- See [INDEX.md](INDEX.md) for organized categories

## 📝 Contributing to Documentation

When adding new documentation:

1. **Place in appropriate location**
   - User guides → `help/`
   - Technical docs → root `docs/`
   - Troubleshooting → `troubleshooting/`

2. **Update the index**
   - Add entry to [INDEX.md](INDEX.md)
   - Update [help/whats-new.md](help/whats-new.md) if user-facing

3. **Use clear naming**
   - Feature docs: `FEATURE_NAME_FEATURE.md`
   - Implementation: `IMPLEMENTATION_NAME_COMPLETE.md`
   - Guides: `GUIDE_NAME_GUIDE.md`

4. **Include metadata**
   - Date created/updated
   - Version number if applicable
   - Related documentation links

## ⚠️ Important Notes

### Docker Development
**Always read [DOCKER_SETUP_REFERENCE.md](DOCKER_SETUP_REFERENCE.md) before making changes to:**
- docker-compose.yml
- Dockerfile (frontend or backend)
- Port configurations
- Build processes

**Key principle:** Bind mounts = no rebuilds needed for code changes

### Authentication
Authentication is handled by the React app (not nginx):
- Uses Bearer tokens from `/auth/login`
- All API calls must use `api` client (not raw axios)
- See [AUTHENTICATION_COMPLETE.md](AUTHENTICATION_COMPLETE.md)

### Deprecated Features
Check [DEPRECATED_FEATURES.md](DEPRECATED_FEATURES.md) before implementing features that may have been removed or replaced.

## 📞 Getting Help

1. Check [INDEX.md](INDEX.md) for relevant documentation
2. Search existing docs for keywords
3. Check [troubleshooting/](troubleshooting/) for common issues
4. Review [help/whats-new.md](help/whats-new.md) for recent changes

## 🗂️ Maintenance

### Regular Tasks
- Update [help/whats-new.md](help/whats-new.md) with new features
- Keep [INDEX.md](INDEX.md) current
- Archive outdated status documents
- Update version numbers in documentation

### Archive Candidates
Documents that are outdated and should be moved to an archive folder:
- WEEK2_COMPLETE.md, WEEK3_PLAN.md, WEEK3_PROGRESS.md
- PHASE1_INTEGRATION_TESTS.md (if phases are complete)
- REFACTORING_STATUS.md, REFACTORING_PROGRESS.md (if refactoring done)
- Old implementation plans that have been completed

---

**Last Updated:** December 18, 2025  
**Current Version:** 5.1.0  
**Latest Feature:** Management Response Extraction
