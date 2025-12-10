# Frontend Components

## Overview

The frontend is built with React 18.2 and Material-UI 7, providing an intuitive interface for SOC report analysis.

## Technology Stack

- **React 18.2**: Component framework
- **Material-UI 7**: UI component library
- **TypeScript**: Type-safe development
- **React Router 6**: Client-side routing
- **Axios**: HTTP client
- **Socket.IO**: Real-time updates
- **React Markdown**: Help system rendering
- **React Virtualized**: Efficient list rendering
- **Recharts**: Data visualization

## Main Pages

### AnalyzerPage (`src/pages/AnalyzerPage.tsx`)
Landing page for PDF upload and scan initiation:
- Drag-and-drop file upload
- Report type detection
- Real-time progress tracking
- Extractor checklist display
- Scan history with virtual grid

### ReportPage (`src/pages/ReportPage.tsx`)
Comprehensive report viewer with tabbed interface:
- **Summary Tab**: High-level metrics and report info
- **Controls Tab**: Editable control data table
- **Deviations Tab**: Controls with exceptions
- **CUECs Tab**: User entity controls
- **Subservice Orgs Tab**: Third-party vendors
- **Company Info Tab**: Service organization details
- **Executive Summary Tab**: AI-generated summary

### SettingsPage (`src/pages/SettingsPage.tsx`)
System configuration:
- GPT model selection
- Confidence weight tuning
- Docker container management
- Token budget configuration

### ValidationPage (`src/pages/ValidationPage.tsx`)
SOC 1 baseline management:
- Baseline creation
- Regression detection
- Side-by-side comparison

## Key Components

### EditableTable (`src/components/EditableTable.tsx`)
Reusable data table with:
- Inline editing
- Sorting and filtering
- Batch edit mode
- Custom cell renderers
- Row selection

### HistoryCard (`src/components/HistoryCard.tsx`)
Scan history display card showing:
- Company name and logo
- Report type badge
- Scan timestamp
- Control count

### VirtualHistoryGrid (`src/components/VirtualHistoryGrid.tsx`)
Efficient rendering of scan history using react-virtualized.

### HelpDialog (`src/components/HelpDialog.tsx`)
Contextual help system:
- Markdown rendering
- Syntax highlighting
- Searchable topics
- Deep linking support

### MergeSuggestionsPanel (`src/components/report/tables/MergeSuggestionsPanel.tsx`)
Control merge interface:
- Side-by-side comparison
- Ignore/Dismiss/Link/Merge actions
- Duplicate instance handling
- Confidence impact display

## Routing

- `/`: Analyzer page (upload and scan)
- `/app/report/:scanId`: Report viewer
- `/app-settings`: Settings page
- `/validation`: SOC 1 validation

## State Management

- React hooks (useState, useEffect, useMemo)
- Local storage for preferences
- API-driven data fetching
- WebSocket for live updates

## Styling

- Material-UI theme system
- Custom Solidigm brand colors
- Dark mode support (available but not default)
- Responsive design with breakpoints
