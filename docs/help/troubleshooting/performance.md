# Performance Tips

## Extraction Performance

### Optimize PDF Size
- **Compress PDFs**: Use PDF compression tools
- **Remove unnecessary pages**: Extract only relevant sections
- **Target**: Keep PDFs under 10 MB when possible

### Chunking Configuration
Adjust chunk size for better performance:
- **Smaller chunks**: Faster individual processing
- **Larger chunks**: Better context, fewer API calls
- **Sweet spot**: 1000-1500 tokens per chunk
- **Overlap**: 200-300 tokens

### Parallel Processing
Enable parallel extractor execution:
- Multiple extractors run simultaneously
- Reduces overall scan time
- Monitor CPU usage

## Database Performance

### Index Optimization
Ensure indexes exist on:
- `scan_id` columns
- `control_id` columns
- Foreign key columns

### Connection Pooling
Configure connection pool:
- **Pool size**: 10-20 connections
- **Max overflow**: 5-10
- **Pool timeout**: 30 seconds

### Query Optimization
- Use pagination for large result sets
- Avoid `SELECT *` when possible
- Index frequently queried columns

## Frontend Performance

### Virtual Scrolling
Large control lists use virtual scrolling:
- Only renders visible rows
- Handles 1000+ controls smoothly
- Minimal memory footprint

### Lazy Loading
- Load data on-demand
- Defer non-critical resources
- Use skeleton loaders

### Caching
- Browser cache for static assets
- Local storage for preferences
- Redis cache for frequent queries

## Network Performance

### API Response Size
Reduce payload size:
- Return only needed fields
- Use pagination
- Compress responses

### WebSocket Efficiency
- Batch progress updates
- Throttle event frequency
- Close inactive connections

### CDN Usage
Consider CDN for:
- Static frontend assets
- Company logos
- Help documentation

## Docker Performance

### Resource Allocation
Adjust Docker Desktop settings:
- **CPUs**: 4-6 cores
- **Memory**: 8-12 GB
- **Swap**: 2-4 GB

### Volume Performance
- Use named volumes (faster than bind mounts)
- Minimize file system operations
- Cache frequently accessed data

### Container Health
Monitor container resources:
```powershell
docker stats
```

## GPT API Performance

### Model Selection
- **GPT-4**: Higher quality, slower, more expensive
- **GPT-3.5-turbo**: Faster, cheaper, good quality
- Use GPT-3.5-turbo for initial extraction
- Use GPT-4 for quality checks

### Prompt Optimization
- Clear, concise prompts
- Structured output format
- Minimize token usage
- Reuse successful prompts

### Batch Processing
- Group similar requests
- Use async API calls
- Implement retry logic with backoff

## Monitoring

### Key Metrics
Track performance indicators:
- Scan completion time
- Controls extracted per minute
- API response times
- Error rates

### Logging
- Enable detailed logging for troubleshooting
- Disable verbose logging in production
- Rotate logs regularly

### Alerts
Set up alerts for:
- Scan failures
- Slow API responses
- High error rates
- Resource exhaustion

## Best Practices

### Scan Scheduling
- Run large scans during off-hours
- Stagger multiple scans
- Limit concurrent scans to 2-3

### Maintenance
- Regular database vacuuming
- Clear Redis cache periodically
- Update Docker images
- Monitor disk space

### Capacity Planning
- Estimate tokens needed per report
- Plan API quota allocation
- Scale resources as needed
- Archive old scans

## Performance Benchmarks

### Typical Scan Times
- Small report (< 50 controls): 2-4 minutes
- Medium report (50-150 controls): 5-10 minutes
- Large report (150+ controls): 10-20 minutes

### Factors Affecting Performance
- Report size and complexity
- PDF text quality
- Network latency
- GPT API response time
- Database size
- Concurrent scan load

## Troubleshooting Slow Performance

### Identify Bottleneck
1. Check CPU usage: `docker stats`
2. Monitor network: Browser dev tools
3. Review logs for timeouts
4. Profile slow endpoints

### Common Causes
- Insufficient Docker resources
- Network congestion
- Database not optimized
- GPT API rate limiting
- Large file uploads

### Quick Fixes
- Restart Docker containers
- Clear browser cache
- Optimize database indexes
- Reduce chunk size
- Use faster GPT model
