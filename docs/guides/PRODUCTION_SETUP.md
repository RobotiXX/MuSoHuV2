# MuSoHu Web Service - Production Setup Guide

> Historical deployment notes. For the current MuSoHuV2 workspace, use
> [web-app/README.md](../../web-app/README.md) and
> [scripts/deploy/README.md](../../scripts/deploy/README.md). The helper now runs
> as the normal user, defaults to preparation only, and installs only with
> `--install`. Old port/resource-limit examples below do not describe the
> current service template.


This guide explains how to set up the MuSoHu web application as a systemd service with automatic restart, resource limits, and centralized logging.

## Features

- **Automatic Restart on Failure** - Service restarts automatically if it crashes  
- **Unlimited Restart Attempts** - No limit on restart attempts with 10-second delay  
- **ASGI Server** - Uvicorn handles async requests  
- **FastAPI Framework** - Async web framework  
- **Auto-start on Boot** - Service starts automatically when system boots  
- **Resource Limits** - CPU (50%) and Memory (1GB) limits  
- **Centralized Logging** - Logs sent to systemd journal  
- **Health Check Endpoint** - `/api/health` endpoint for monitoring  
- **Standard HTTP Port** - Port 80 for web access  

## Quick Setup

### 1. Install the Production Service

```bash
# Navigate to project root
cd /path/to/MuSoHu

# Run the setup script with sudo
sudo bash scripts/deploy/setup_production_web_service.sh
```

This script will:
- Create/activate Python virtual environment
- Install all dependencies including Waitress
- Create systemd service file
- Enable and start the service
- Configure firewall (if UFW is active)
- Verify installation

### 2. Verify Installation

```bash
# Check service status
sudo systemctl status musohu-web

# Test health endpoint
curl http://localhost/api/health

# View recent logs
sudo journalctl -u musohu-web -n 50
```

## Service Management

### Using the Management Script (Recommended)

```bash
# Start the service
sudo bash scripts/utils/manage_web_service.sh start

# Stop the service
sudo bash scripts/utils/manage_web_service.sh stop

# Restart the service
sudo bash scripts/utils/manage_web_service.sh restart

# Check status and statistics
bash scripts/utils/manage_web_service.sh status
bash scripts/utils/manage_web_service.sh stats

# View logs
bash scripts/utils/manage_web_service.sh logs      # Last 50 lines
bash scripts/utils/manage_web_service.sh logs 100  # Last 100 lines
bash scripts/utils/manage_web_service.sh follow    # Real-time logs

# Health check
bash scripts/utils/manage_web_service.sh health

# Run connectivity tests
bash scripts/utils/manage_web_service.sh test

# Enable/disable auto-start
sudo bash scripts/utils/manage_web_service.sh enable
sudo bash scripts/utils/manage_web_service.sh disable
```

### Using systemctl Directly

```bash
# Start/Stop/Restart
sudo systemctl start musohu-web
sudo systemctl stop musohu-web
sudo systemctl restart musohu-web

# Status
sudo systemctl status musohu-web

# Enable/Disable auto-start on boot
sudo systemctl enable musohu-web
sudo systemctl disable musohu-web

# View logs
sudo journalctl -u musohu-web           # All logs
sudo journalctl -u musohu-web -f        # Follow logs
sudo journalctl -u musohu-web -n 50     # Last 50 lines
sudo journalctl -u musohu-web --since "1 hour ago"

# Check restart count
sudo systemctl show musohu-web -p NRestarts
```

## Configuration

### Service Configuration File

Location: `/etc/systemd/system/musohu-web.service`

Key configuration options:

```ini
[Service]
# Restart policy
Restart=always              # Always restart on failure
RestartSec=10              # Wait 10 seconds before restart
StartLimitBurst=0          # No limit on restart attempts

# Resource limits
MemoryMax=1G               # Maximum memory: 1GB
MemoryHigh=800M            # Soft memory limit: 800MB
CPUQuota=50%               # CPU usage limit: 50%

# Logging
StandardOutput=journal     # Send stdout to journal
StandardError=journal      # Send stderr to journal
SyslogIdentifier=musohu-web
```

### Application Configuration

Location: `web-app/config.yml`

```yaml
server:
  host: '0.0.0.0'
  port: 80           # Standard HTTP port (requires sudo)
  debug: false       # Set to false for production

log_viewer:
  max_lines: 100
  # ... other settings
```

**Note**: Port 80 requires root/sudo privileges. The systemd service handles this automatically.

### Modifying Resource Limits

Edit the service file:

```bash
sudo nano /etc/systemd/system/musohu-web.service
```

Change values:
```ini
MemoryMax=2G      # Increase to 2GB
CPUQuota=100%     # Use full CPU
```

Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart musohu-web
```

## Production Server (Uvicorn)

The application uses Uvicorn ASGI server in production:

### Features:
- Async/await support for concurrency
- WebSocket support
- HTTP/2 support (with additional configuration)
- Suitable for async applications

### Running with Multiple Workers:

For better performance on multi-core systems, you can run multiple worker processes.

Edit `/etc/systemd/system/musohu-web.service`:
```ini
ExecStart=/path/to/venv/bin/uvicorn app:app --host 0.0.0.0 --port 80 --workers 4
```

### Development vs Production:

The application automatically uses Uvicorn in both modes, but you can enable auto-reload for development:

```bash
# Development (with auto-reload)
uvicorn app:app --host 0.0.0.0 --port 80 --reload

# Production (no reload, optimized)
uvicorn app:app --host 0.0.0.0 --port 80
```

## Health Check Endpoint

The `/api/health` endpoint provides service status information:

```bash
# Check health
curl http://localhost/api/health

# Response:
{
  "status": "healthy",
  "running_scripts": 0,
  "timestamp": "2025-11-12T10:30:00.123456"
}
```

Use this endpoint for:
- Load balancer health checks
- Monitoring systems (Prometheus, Nagios, etc.)
- Automated testing
- Service verification

## Monitoring and Troubleshooting

### Check Service Status

```bash
# Quick status
sudo systemctl is-active musohu-web

# Detailed status
sudo systemctl status musohu-web

# Check if enabled on boot
sudo systemctl is-enabled musohu-web
```

### View Logs

```bash
# Recent logs
sudo journalctl -u musohu-web -n 100

# Logs from last hour
sudo journalctl -u musohu-web --since "1 hour ago"

# Logs with timestamp
sudo journalctl -u musohu-web -o short-precise

# Follow logs in real-time
sudo journalctl -u musohu-web -f

# Filter by log level
sudo journalctl -u musohu-web -p err  # Errors only
```

### Monitor Resource Usage

```bash
# Memory usage
sudo systemctl show musohu-web -p MemoryCurrent

# All resource stats
sudo systemd-cgtop -1 | grep musohu-web

# Check restart count
sudo systemctl show musohu-web -p NRestarts

# View process information
ps aux | grep "python.*app.py"
```

### Common Issues

#### Service Won't Start

```bash
# Check detailed error
sudo journalctl -u musohu-web -n 50 --no-pager

# Check if port is in use
sudo ss -tuln | grep :80

# Check file permissions
ls -la /path/to/web-app/
```

#### Service Keeps Restarting

```bash
# Check restart count
sudo systemctl show musohu-web -p NRestarts

# View logs around restart
sudo journalctl -u musohu-web --since "10 minutes ago"

# Check for Python errors
sudo journalctl -u musohu-web | grep -i error
```

#### High Memory Usage

```bash
# Check current memory
sudo systemctl show musohu-web -p MemoryCurrent

# Adjust memory limit if needed
sudo nano /etc/systemd/system/musohu-web.service
# Change MemoryMax value
sudo systemctl daemon-reload
sudo systemctl restart musohu-web
```

## Uninstall

To remove the service:

```bash
# Stop and disable service
sudo systemctl stop musohu-web
sudo systemctl disable musohu-web

# Remove service file
sudo rm /etc/systemd/system/musohu-web.service

# Reload systemd
sudo systemctl daemon-reload

# Reset failed units
sudo systemctl reset-failed
```

## Advanced Configuration

### Custom Systemd Options

Add to service file under `[Service]` section:

```ini
# Watchdog (requires app support)
WatchdogSec=30

# Nice level (priority)
Nice=-5

# Number of file descriptors
LimitNOFILE=65535

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
```

### Email Notifications on Failure

Install and configure:
```bash
sudo apt install mailutils
```

Add to service file:
```ini
[Unit]
OnFailure=failure-notification@%n.service
```

### Multiple Instances

To run multiple instances on different ports:

```bash
# Copy and modify service file
sudo cp /etc/systemd/system/musohu-web.service \
       /etc/systemd/system/musohu-web-2.service

# Edit new file to use different port
sudo nano /etc/systemd/system/musohu-web-2.service

# Start both services
sudo systemctl start musohu-web musohu-web-2
```

## Integration with Monitoring Systems

### Prometheus

Use the health endpoint:
```yaml
scrape_configs:
  - job_name: 'musohu-web'
    static_configs:
      - targets: ['localhost:5001']
    metrics_path: '/health'
```

### Systemd Watchdog

Enable in service file:
```ini
WatchdogSec=30
Type=notify
```

Add to app.py:
```python
import systemd.daemon
systemd.daemon.notify('WATCHDOG=1')
```

## Best Practices

1. **Always use production mode** - Set `debug: false` in config.yml
2. **Monitor logs regularly** - Check for errors and warnings
3. **Set appropriate resource limits** - Prevent runaway processes
4. **Enable auto-start** - Ensure service starts on boot
5. **Test health endpoint** - Verify service is responding
6. **Review restart count** - Investigate if count is high
7. **Keep dependencies updated** - Regularly update pip packages
8. **Backup configuration** - Keep copies of service file and config.yml

## Files Created

- `/etc/systemd/system/musohu-web.service` - Systemd service file
- `scripts/deploy/templates/musohu-web.service.template` - Service template
- `scripts/deploy/setup_production_web_service.sh` - Setup script
- `scripts/utils/manage_web_service.sh` - Management script

## Support

For issues or questions:
1. Check logs: `sudo journalctl -u musohu-web -n 100`
2. Run tests: `bash scripts/utils/manage_web_service.sh test`
3. Review this documentation
4. Check GitHub issues

## References

- [Systemd Service Documentation](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Uvicorn Documentation](https://www.uvicorn.org/)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
