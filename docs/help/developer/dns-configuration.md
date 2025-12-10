# DNS Configuration for Dataiku DSS

## Problem

Intermittent DNS resolution failures for `dataiku-dss.corp.nandps.com` can cause long delays when the corporate DNS server is unreachable.

## Solution

Hard-code the Dataiku DSS server IP address to bypass DNS resolution entirely.

## Setup Steps

### 1. Find the IP address of your Dataiku server

**Windows (PowerShell):**
```powershell
Resolve-DnsName dataiku-dss.corp.nandps.com
```

**Linux/Mac:**
```bash
nslookup dataiku-dss.corp.nandps.com
# or
dig dataiku-dss.corp.nandps.com +short
```

Example output:
```
Name:    dataiku-dss.corp.nandps.com
Address: 10.50.100.25
```

### 2. Add the IP to your `.env` file

Open `.env` and add this line with your actual IP:

```bash
# DNS Fallback for Dataiku (optional but recommended)
DATAIKU_DSS_HOST_IP=10.50.100.25
```

**Important Notes:**
- Replace `10.50.100.25` with your actual Dataiku server IP
- Leave blank or comment out if you don't want DNS fallback
- The hostname in `DATAIKU_DSS_HOST` should still use the full domain name

### 3. Rebuild and restart

```powershell
.\socanalyzer.ps1 rebuild
```

## How It Works

When `DATAIKU_DSS_HOST_IP` is set:

1. **DNS Resolution Bypass** - Python's socket layer is patched to resolve `dataiku-dss.corp.nandps.com` directly to the hardcoded IP
2. **Logging** - A `phase=dns_fallback` event is written to `gpt_calls.log` when activated
3. **Normal Operation** - If DNS is working normally, the IP fallback has no negative impact

**Note:** An earlier timeout mechanism using `signal.alarm()` was removed because it doesn't work in worker threads. The DNS fallback is now the primary defense against DNS-related delays.

Example log entry:
```json
{
  "ts": 1762821586.0665,
  "phase": "dns_fallback",
  "provider": "dataiku_dss",
  "hostname": "dataiku-dss.corp.nandps.com",
  "ip": "10.50.100.25"
}
```

## Verification

After setup, check the logs to confirm DNS fallback is active:

```powershell
Get-Content .\data\logs\gpt_calls.log | Select-String dns_fallback
```

If you see the log entry, DNS fallback is working correctly.

## Docker DNS Cache

The Docker environment includes a DNS cache service to reduce corporate DNS load:

### Configuration
In `docker-compose.yml`:
```yaml
dns-cache:
  image: jpillora/dnsmasq
  restart: unless-stopped
  networks:
    socanalyzer_network:
      ipv4_address: 172.20.0.2
```

### Usage
Other Docker containers are configured to use the DNS cache:
```yaml
dns:
  - 172.20.0.2  # Internal DNS cache
  - 8.8.8.8     # Google DNS fallback
```

This provides:
- **Caching** - Reduces repeated DNS lookups
- **Fallback** - If corporate DNS fails, uses Google DNS
- **Performance** - Faster resolution for frequently-accessed domains

## When to Use

✅ **Use DNS fallback when:**
- Corporate DNS is unreliable or slow
- Working from home/VPN with intermittent connectivity
- You frequently see "Temporary failure in name resolution" errors
- Extraction jobs take abnormally long to start

❌ **Don't use DNS fallback when:**
- Dataiku server IP changes frequently (DHCP)
- You're on a stable corporate network with reliable DNS
- Security policy prohibits IP-based connections

## Troubleshooting

### SSL Certificate Errors

If you get SSL errors after enabling DNS fallback, the certificate might be tied to the hostname.

**Solutions:**

1. **Disable SSL verification** (not recommended for production):
   ```bash
   DATAIKU_VERIFY_SSL=false
   ```

2. **Use hostname-based connection** (leave `DATAIKU_DSS_HOST_IP` blank)

### IP Address Changed

If the server IP changes, you'll see connection errors.

**Fix:**
```powershell
# Find new IP
Resolve-DnsName dataiku-dss.corp.nandps.com

# Update .env with new IP
# DATAIKU_DSS_HOST_IP=10.50.100.XX

# Rebuild
.\socanalyzer.ps1 rebuild
```

### DNS Still Slow

If DNS is still causing delays:

1. Check Docker DNS cache is running:
   ```powershell
   docker ps | Select-String dns-cache
   ```

2. Verify containers are using DNS cache:
   ```powershell
   docker inspect socanalyzer-backend | Select-String "172.20.0.2"
   ```

3. Check DNS cache logs:
   ```powershell
   docker logs socanalyzer-dns-cache
   ```

## Security Note

Storing IP addresses bypasses DNS security features (like DNS-based load balancing and dynamic updates).

Only use this fallback if:
- You trust the network path to the IP
- The IP is static or rarely changes
- DNS failures are causing significant operational issues

For production environments, consider fixing the root DNS issue instead of relying on IP fallback.

## Related Configuration

### Dataiku Connection Settings

In `.env`:
```bash
# Dataiku DSS connection
DATAIKU_DSS_HOST=dataiku-dss.corp.nandps.com
DATAIKU_DSS_PORT=443
DATAIKU_DSS_API_KEY=<your-api-key>
DATAIKU_DSS_PROJECT_KEY=<your-project>

# DNS Fallback (optional)
DATAIKU_DSS_HOST_IP=10.50.100.25

# SSL Verification (optional)
DATAIKU_VERIFY_SSL=true
```

### GPT Client Implementation

The DNS fallback is implemented in `backend/app/gpt_client.py`:

```python
# If DATAIKU_DSS_HOST_IP is set, patch socket resolution
if config.DATAIKU_DSS_HOST_IP:
    import socket
    original_getaddrinfo = socket.getaddrinfo
    
    def custom_getaddrinfo(host, port, *args, **kwargs):
        if host == config.DATAIKU_DSS_HOST:
            # Use hardcoded IP
            return [(2, 1, 6, '', (config.DATAIKU_DSS_HOST_IP, port))]
        return original_getaddrinfo(host, port, *args, **kwargs)
    
    socket.getaddrinfo = custom_getaddrinfo
```

## Further Reading

- See **GPT Model Configuration** for Dataiku LLM setup
- See **Troubleshooting > Common Errors** for connection issues
- See **Architecture > Backend Services** for GPT client details
