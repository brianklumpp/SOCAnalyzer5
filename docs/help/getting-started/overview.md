# System Overview

## What is SOC Analyzer?

SOC Analyzer is an intelligent document analysis system designed to extract, analyze, and manage information from SOC 1 and SOC 2 audit reports. The system uses AI-powered extraction to automatically identify controls, CUECs (Complementary User Entity Controls), subservice organizations, and other critical audit information.

## Key Capabilities

### Automated Extraction
- **PDF Processing**: Converts audit reports to structured data
- **GPT-Powered Analysis**: Uses large language models to understand context and extract information
- **Multi-Framework Support**: Maps controls to TSC and COSO frameworks
- **Confidence Scoring**: Assigns quality scores to all extracted data

### Data Management
- **Control Organization**: Groups controls by framework sections
- **Deviation Tracking**: Identifies and highlights control deviations
- **Duplicate Detection**: Automatically finds and merges duplicate controls
- **Batch Editing**: Efficiently edit multiple records simultaneously

### Quality Assurance
- **Automated Cleanup**: Post-extraction validation and error flagging
- **Confidence Thresholds**: Filters low-quality extractions (< 75%)
- **Merge History**: Full audit trail of all merge operations
- **Pattern Learning**: Learns from verified controls to improve accuracy

## System Components

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │────▶│  PostgreSQL │
│  React/MUI  │     │   FastAPI   │     │   Database  │
└─────────────┘     └─────────────┘     └─────────────┘
       │                    │                    
       │                    ▼                    
       │            ┌─────────────┐              
       └───────────▶│    Redis    │              
                    │  WebSocket  │              
                    └─────────────┘              
```

### Frontend
- React 18 with TypeScript
- Material-UI component library
- Real-time WebSocket updates
- Responsive design for desktop and mobile

### Backend
- FastAPI async Python framework
- GPT integration for AI extraction
- Alembic database migrations
- RESTful API with comprehensive endpoints

### Database
- PostgreSQL 15 for structured data
- JSON fields for flexible metadata
- Full-text search capabilities
- Optimized indexes for performance

### Infrastructure
- Docker Compose orchestration
- Redis for caching and real-time updates
- DNS cache for improved resolution
- Health monitoring and logging

## Typical Workflow

1. **Upload Report**: Upload SOC 1/2 PDF report via web interface
2. **Automated Extraction**: System processes PDF and extracts all data
3. **Review & Edit**: Review extracted controls, CUECs, and organizations
4. **Merge Duplicates**: System suggests or auto-merges duplicate controls
5. **Generate Summary**: AI creates executive summary of findings
6. **Export**: Download results or integrate with other systems

## Next Steps

- [Quick Start Guide](#quick-start) - Get started in minutes
- [Architecture Overview](#architecture-overview) - Deep dive into system design
- [Extraction Workflow](#extraction-workflow) - How data extraction works
