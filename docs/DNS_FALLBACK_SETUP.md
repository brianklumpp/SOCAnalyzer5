# DNS Fallback Configuration

## Problem
Intermittent DNS resolution failures for `dataiku-dss.corp.nandps.com` can cause long delays when the corporate DNS server is unreachable.

## Solution
Hard-code the Dataiku DSS server IP address to bypass DNS resolution entirely when configured.

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

1. **DNS Resolution Bypass**: The system patches Python's socket layer to resolve `dataiku-dss.corp.nandps.com` directly to the hardcoded IP address
2. **Logging**: A `phase=dns_fallback` event is written to `gpt_calls.log` when the fallback activates
3. **Normal Operation**: If DNS is working normally, the IP fallback has no negative impact

**Note**: An earlier timeout mechanism using `signal.alarm()` was removed because it doesn't work in worker threads. The DNS fallback is now the primary defense against DNS-related delays.

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

## When to Use

✅ **Use DNS fallback when:**
- Corporate DNS is unreliable or slow
- Working from home/VPN with intermittent connectivity
- You frequently see "Temporary failure in name resolution" errors

❌ **Don't use DNS fallback when:**
- Dataiku server IP changes frequently (DHCP)
- You're on a stable corporate network with reliable DNS
- Security policy prohibits IP-based connections

## Troubleshooting

### SSL Certificate Errors
If you get SSL errors after enabling DNS fallback, the certificate might be tied to the hostname. Solutions:

1. **Disable SSL verification** (not recommended for production):
   ```bash
   DATAIKU_VERIFY_SSL=false
   ```

2. **Use hostname-based connection** (leave `DATAIKU_DSS_HOST_IP` blank)

### IP Address Changed
If the server IP changes, you'll see connection errors. Update `.env` with the new IP and rebuild:

```powershell
# Find new IP
Resolve-DnsName dataiku-dss.corp.nandps.com

# Update .env with new IP
# DATAIKU_DSS_HOST_IP=10.50.100.XX

# Rebuild
.\socanalyzer.ps1 rebuild
```

## Security Note

Storing IP addresses bypasses DNS security features (like DNS-based load balancing and dynamic updates). Only use this fallback if:

- You trust the network path to the IP
- The IP is static or rarely changes
- DNS failures are causing significant operational issues

For production environments, consider fixing the root DNS issue instead of relying on IP fallback.
