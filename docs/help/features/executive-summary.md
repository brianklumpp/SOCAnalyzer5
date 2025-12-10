# Executive Summary

## Overview

The Executive Summary feature uses AI to generate comprehensive narrative summaries of SOC audit reports, providing stakeholders with digestible insights from complex technical data.

## Generation Process

### Automatic Generation
Executive summaries are automatically generated:
- After successful scan completion
- Triggered during data insertion
- Runs in background
- Takes 30-60 seconds

### Data Inputs
Summary generation considers:
- All extracted controls
- Deviation information
- Framework coverage (TSC, COSO)
- Company information
- Report metadata
- Test results

### AI Prompt
GPT-4 receives structured prompt with:
- Report context
- Control summaries (prioritizing deviations)
- Coverage statistics
- Token budgets to prevent truncation

## Summary Content

### Standard Sections

#### Report Overview
- Service organization name
- Report type (SOC 1 Type 2, SOC 2 Type 2)
- Coverage period
- Auditor information

#### Scope
- Service/product description
- System boundaries
- Framework criteria covered
- Control categories

#### Key Findings
- Total controls tested
- Controls without exceptions
- Number of deviations
- Deviation highlights

#### Framework Coverage
- TSC criteria coverage percentage
- COSO principle coverage
- Gap analysis
- Untested areas

#### Recommendations
- Areas for improvement
- Risk considerations
- Next steps

## Viewing the Summary

### Executive Summary Tab
Access from report page:
1. Click "Executive Summary" tab
2. Scroll to read full summary
3. Copy text for external use
4. Export as PDF if needed

### Summary Display
- Formatted markdown rendering
- Proper headings and lists
- Easy-to-read typography
- Print-friendly layout

## Regeneration

### When to Regenerate
Regenerate summary after:
- Editing control descriptions
- Updating deviation information
- Merging controls
- Correcting extraction errors

### How to Regenerate
1. Click "Regenerate Summary" button
2. Confirm action
3. Wait 30-60 seconds
4. New summary replaces old

### Token Management
If regeneration fails:
- Check token limits
- Reduce control descriptions
- Adjust budget in settings
- Contact support

## Customization

### Settings Configuration
Adjust generation parameters:
- **Max Controls**: Limit non-deviation controls included
- **Chars per Control**: Character budget per control
- **Test Results Budget**: Total chars for test results
- **Token Warning**: Alert threshold

### Prompt Tuning
Advanced users can modify:
- Summary structure
- Section emphasis
- Tone and style
- Technical depth

## Use Cases

### Stakeholder Communication
- Board presentations
- Management updates
- Client deliverables
- Audit committee reports

### Internal Review
- Quality control check
- Peer review
- File documentation
- Knowledge transfer

### Compliance
- Regulatory submissions
- External audit support
- Risk assessments
- Due diligence

## Best Practices

1. **Review Before Sharing**: Always validate AI-generated content
2. **Customize as Needed**: Edit summary for specific audiences
3. **Regenerate After Changes**: Keep summary current with data updates
4. **Supplement with Details**: Use summary as overview, not replacement for full report
5. **Version Control**: Save copies before regenerating

## Limitations

- **AI Interpretation**: May not capture all nuances
- **Token Limits**: Very large reports may be truncated
- **Accuracy**: Verify key facts and figures
- **Context**: AI lacks domain expertise
- **Confidentiality**: Review for sensitive information

## Troubleshooting

### Summary Too Short
- Increase token budgets
- Include more controls
- Adjust character limits

### Summary Too Long
- Reduce max controls
- Lower character budgets
- Focus on deviations only

### Generation Fails
- Check API connectivity
- Verify token quotas
- Review error messages
- Retry after delay

### Inaccurate Content
- Verify source data
- Check extraction quality
- Regenerate after corrections
- Manual edit if needed
