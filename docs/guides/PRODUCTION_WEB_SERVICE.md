# MuSoHu Production Web Service Setup

> Historical deployment notes. For the current MuSoHuV2 workspace, use
> [web-app/README.md](../../web-app/README.md) and
> [scripts/deploy/README.md](../../scripts/deploy/README.md). The helper now runs
> as the normal user, defaults to preparation only, and installs only with
> `--install`. Old port/resource-limit examples below do not describe the
> current service template.


Production setup for the MuSoHu web application with automatic restart, resource limits, and deployment features.

---

## Development vs Production

### Development Mode (Port 8000, No sudo required)

**For testing and development:**

```bash
# 1. Navigate to web-app directory
cd /path/to/MuSoHu/web-app

# 2. Activate virtual environment and install dependencies
source ../.venv/bin/activate
pip install -r requirements.txt

# 3. Run development server with auto-reload
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# 4. Access at http://localhost:8000
```

**Development Features:**
- Auto-reload on code changes
- No sudo required (runs on port 8000)
- Detailed error messages
- Interactive API docs at `/docs`

**Use when:** Testing, developing features, debugging

---

### Production Mode - Option 1: User Port (No sudo)

For production without sudo (runs on port 8000):

```bash
# 1. Navigate to web-app directory
cd /path/to/MuSoHu/web-app

# 2. Activate virtual environment
source ../.venv/bin/activate

# 3. Run production server (without reload)
uvicorn app:app --host 0.0.0.0 --port 8000

# 4. Access at http://localhost:8000
```

**To run in background:**
```bash
# Option A: Using nohup
nohup ../.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 > logs/uvicorn.log 2>&1 &

# Option B: Using screen
screen -dmS musohu-web ../.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000

# Option C: Using tmux
tmux new-session -d -s musohu-web '../.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000'
```

Production Features:
- No sudo required
- Runs on port 8000 (non-privileged)
- No reload
- Can use systemd user service
- Does not require root privileges

Use when: Production deployment, security is priority, port 80 not required

---

### Production Mode - Option 2: System Service (Requires sudo)

For production with systemd on port 80:

```bash
# One-command setup
sudo bash scripts/deploy/setup_production_web_service.sh
```

Production Features:
- Runs on port 80 (standard HTTP)
- Automatic restart on failure
- Systemd integration
- Resource limits
- Auto-start on boot
- Requires sudo for setup

Use when: Port 80 required, systemd auto-restart needed, deploying to production server

Note: Port 80 requires root privileges. Alternatives:
- Use port 8000 (no sudo)
- Use reverse proxy (nginx/Apache) forwarding from port 80
- Use `setcap` to allow port binding without sudo (Linux only)

---

---

## Best Practices

1. Use production mode - Set `debug: false` in config.yml
2. Monitor logs regularly - Check for errors and warnings
3. Set appropriate resource limits
4. Enable auto-start - Service starts on boot
5. Test health endpoint - Verify service is responding
6. Review restart count - Investigate if count is high
7. Keep dependencies updated - Update pip packages regularly
8. Backup configuration - Keep copies of service file and config.yml

## Quick Start

```bash
# 1. Navigate to project directory
cd /path/to/MuSoHu

# 2. Run production setup
sudo bash scripts/deploy/setup_production_web_service.sh

# 3. Verify installation
bash scripts/test/test_production_setup.sh

# 4. Access web interface
curl http://localhost/api/health
# Open browser: http://localhost
```

The production web service will run with automatic restart capabilities.

---

## Features

| Feature | Description | Benefit |
|---------|-------------|---------|
| **Automatic Restart** | `Restart=always` | Service restarts on crash |
| **Unlimited Restarts** | `StartLimitBurst=0` | No limit on restart attempts |
| **Restart Delay** | `RestartSec=10` | 10-second delay between restarts |
| **Production Server** | Uvicorn ASGI | Async server for FastAPI |
| **FastAPI Framework** | Async framework | Async request handling |
| **Resource Limits** | 256MB RAM, 25% CPU | Resource constraints |
| **Systemd Logging** | Journal integration | Centralized log management |
| **Auto-start** | Boot integration | Starts automatically on system boot |
| **Health Checks** | `/api/health` endpoint | Monitor service health easily |
| **Security** | Process isolation | NoNewPrivileges, PrivateTmp |
| **Standard Port** | Port 80 | No port number needed in URLs |

---

## What Gets Installed

### Files Created:
- `/etc/systemd/system/musohu-web.service` - Systemd service file
- `web-app/venv/` - Python virtual environment  
- All dependencies including Uvicorn ASGI server

### Files Modified:
- `web-app/requirements.txt` - Updated with FastAPI dependencies
- `web-app/app.py` - FastAPI application with async support

### Scripts Available:
- `scripts/deploy/setup_production_web_service.sh` - Installation script
- `scripts/utils/manage_web_service.sh` - Easy management tool
- `scripts/test/test_production_setup.sh` - Verification tests

---

## Documentation

- **[PRODUCTION_SETUP.md](PRODUCTION_SETUP.md)** - Complete setup guide with all details
- **[CHANGES_SUMMARY.md](CHANGES_SUMMARY.md)** - What was changed and why
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Visual architecture diagrams
- **[QUICK_REFERENCE.md](../reference/QUICK_REFERENCE.md)** - Quick command reference card
- **[INSTALLATION_SUMMARY.md](INSTALLATION_SUMMARY.md)** - Installation overview and next steps

---

## Service Management

### Easy Way (Recommended)

```bash
# Start the service
sudo bash scripts/utils/manage_web_service.sh start

# Stop the service
sudo bash scripts/utils/manage_web_service.sh stop

# Restart the service
sudo bash scripts/utils/manage_web_service.sh restart

# Check status
bash scripts/utils/manage_web_service.sh status

# View logs
bash scripts/utils/manage_web_service.sh logs       # Last 50 lines
bash scripts/utils/manage_web_service.sh follow    # Stream logs

# Check health
bash scripts/utils/manage_web_service.sh health

# Run tests
bash scripts/utils/manage_web_service.sh test

# See all commands
bash scripts/utils/manage_web_service.sh --help
```

### Direct systemctl Commands

```bash
sudo systemctl start musohu-web
sudo systemctl stop musohu-web
sudo systemctl restart musohu-web
sudo systemctl status musohu-web
sudo systemctl enable musohu-web    # Enable auto-start on boot
sudo systemctl disable musohu-web   # Disable auto-start
```

---

## Monitoring

### View Logs

```bash
# Using management script
bash scripts/utils/manage_web_service.sh logs 100   # Last 100 lines
bash scripts/utils/manage_web_service.sh follow    # Real-time

# Using journalctl directly
sudo journalctl -u musohu-web -n 100               # Last 100 lines
sudo journalctl -u musohu-web -f                   # Follow logs
sudo journalctl -u musohu-web --since "1 hour ago" # Time-based
sudo journalctl -u musohu-web -p err               # Errors only
```

### Check Service Status

```bash
# Quick check
sudo systemctl is-active musohu-web

# Detailed status
bash scripts/utils/manage_web_service.sh stats

# Check restart count
sudo systemctl show musohu-web -p NRestarts
```

### Check Health

```bash
# Using management script
bash scripts/utils/manage_web_service.sh health

# Using curl
curl http://localhost/api/health

# Expected response:
{
  "status": "healthy",
  "running_scripts": 0,
  "timestamp": "2025-11-12T10:30:00.123456"
}
```

---

## Testing

### Run Verification Tests

```bash
# Run full test suite
bash scripts/test/test_production_setup.sh
```

This tests:
- File system structure
- Python environment
- Systemd service configuration
- Runtime status
- Network connectivity
- Health endpoint

### Manual Testing

```bash
# 1. Check if service is running
sudo systemctl status musohu-web

# 2. Test health endpoint
curl http://localhost/api/health

# 3. Test web interface
curl http://localhost/

# 4. Test from another machine (replace <your-ip>)
curl http://<your-ip>/api/health

# 5. View recent logs
sudo journalctl -u musohu-web -n 50
```

---

## Configuration

### Application Settings

Edit `web-app/config.yml`:

```yaml
server:
  host: '0.0.0.0'      # Listen on all interfaces
  port: 80             # Standard HTTP port (requires sudo)
  debug: false         # false = Production mode
```

**Note**: Port 80 requires root/sudo privileges. The service runs as your user but binds to port 80 through the systemd service configuration.

### Service Settings

Edit `/etc/systemd/system/musohu-web.service`:

```ini
[Service]
# Restart configuration
Restart=always              # Always restart on failure
RestartSec=10              # Wait 10 seconds before restart
StartLimitBurst=0          # No limit on restart attempts

# Resource limits (lightweight for single user)
MemoryMax=256M             # Maximum memory (sufficient for single user)
MemoryHigh=200M            # Soft limit
CPUQuota=25%               # CPU usage limit (1/4 of one core)

# Adjust as needed for your system
```

After editing, reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart musohu-web
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check detailed logs
sudo journalctl -u musohu-web -n 100

# Check service status
sudo systemctl status musohu-web

# Check if port is already in use
sudo ss -tuln | grep :80

# Kill process on port 80 if needed
sudo lsof -ti:80 | xargs sudo kill -9
```

### Service Keeps Restarting

```bash
# Check restart count
sudo systemctl show musohu-web -p NRestarts

# View logs around restart time
sudo journalctl -u musohu-web --since "10 minutes ago"

# Look for Python errors
sudo journalctl -u musohu-web | grep -i "error\|exception\|traceback"
```

### Port Not Accessible

```bash
# Check if service is listening
sudo ss -tuln | grep :80

# Check firewall
sudo ufw status
sudo ufw allow 80/tcp

# Test locally first
curl http://localhost/api/health

# Then test network access
curl http://$(hostname -I | awk '{print $1}')/api/health
```

### High Memory Usage

```bash
# Check current memory usage
sudo systemctl show musohu-web -p MemoryCurrent

# Adjust memory limit
sudo nano /etc/systemd/system/musohu-web.service
# Change: MemoryMax=2G

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart musohu-web
```

---

## Updating the Service

### Update Application Code

```bash
# 1. Stop the service
sudo systemctl stop musohu-web

# 2. Update code (git pull, edit files, etc.)
cd /path/to/MuSoHu
git pull

# 3. Update dependencies if needed
source web-app/venv/bin/activate
pip install -r web-app/requirements.txt
deactivate

# 4. Restart the service
sudo systemctl start musohu-web

# 5. Verify
bash scripts/utils/manage_web_service.sh test
```

### Reinstall Service

```bash
# Re-run setup script
sudo bash scripts/deploy/setup_production_web_service.sh
```

---

## Uninstall

```bash
# 1. Stop and disable service
sudo systemctl stop musohu-web
sudo systemctl disable musohu-web

# 2. Remove service file
sudo rm /etc/systemd/system/musohu-web.service

# 3. Reload systemd
sudo systemctl daemon-reload
sudo systemctl reset-failed

# 4. (Optional) Remove virtual environment
rm -rf web-app/venv
```

---

## Performance Tips

### When to Adjust Settings

For single user or local use (default):
- Default limits (256MB RAM, 25% CPU) are sufficient for single user
- Typical usage: 50-100MB RAM, <10% CPU
- No changes needed for typical usage

For systems with limited RAM (4-8GB total):
- Keep defaults (256MB RAM limit)
- Reserves less than 4% of system RAM

For multiple concurrent users (5-10+ users) or high RAM systems (16GB+):
- Consider increasing to 512MB-1GB
- Monitor actual usage first before adjusting

### Uvicorn Workers

Single user setup (default):
```ini
# Single process
ExecStart=/path/to/venv/bin/uvicorn app:app --host 0.0.0.0 --port 80
```

Multiple concurrent users (10+ users):
```ini
# Multiple worker processes
ExecStart=/path/to/venv/bin/uvicorn app:app --host 0.0.0.0 --port 80 --workers 2
```

Note: Each worker uses additional memory. Start with 1 worker (default) and only add more if needed.

### Async Performance

FastAPI supports async/await for concurrent performance. The application uses async where appropriate for handling multiple requests efficiently.

### Increase Resource Limits (Only if needed)

Check current usage first:
```bash
# Monitor memory usage
sudo systemctl show musohu-web -p MemoryCurrent

# Monitor CPU usage
top -p $(pgrep -f "uvicorn app:app")
```

Typical usage for single user:
- Memory: 50-100MB (under 256MB limit)
- CPU: 5-15% (under 25% limit)

Only increase if you see:
- Memory consistently over 200MB
- CPU consistently at 25%+
- Application slow under load

Edit `/etc/systemd/system/musohu-web.service`:
```ini
MemoryMax=512M    # Only if memory usage is consistently high
CPUQuota=50%      # Only if CPU usage is consistently high
```

For single user on 8GB system: Default limits (256MB/25% CPU) are appropriate for typical usage.

---

## Security Considerations

The service includes security features:
- Runs as non-root user
- `NoNewPrivileges=true` - Prevents privilege escalation
- `PrivateTmp=true` - Isolated temporary directory
- Resource limits
- Firewall configuration (UFW)

---

## Integration Examples

### With Nginx Reverse Proxy

If you want to add HTTPS or additional security:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /api/health {
        proxy_pass http://localhost:80/api/health;
        access_log off;
    }
}
```

### With Prometheus Monitoring

```yaml
scrape_configs:
  - job_name: 'musohu-web'
    static_configs:
      - targets: ['localhost:80']
    metrics_path: '/api/health'
```

---

## Additional Resources

- **systemd Documentation**: https://www.freedesktop.org/software/systemd/man/
- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Uvicorn Documentation**: https://www.uvicorn.org/
- **FastAPI Deployment**: https://fastapi.tiangolo.com/deployment/

---

## Getting Help

1. **Run tests**: `bash scripts/test/test_production_setup.sh`
2. **Check logs**: `sudo journalctl -u musohu-web -n 100`
3. **View status**: `bash scripts/utils/manage_web_service.sh stats`
4. **Read docs**: See [PRODUCTION_SETUP.md](PRODUCTION_SETUP.md)
5. **Quick reference**: See [docs/reference/QUICK_REFERENCE.md](../reference/QUICK_REFERENCE.md)

---

## Quick Checklist

After installation, verify:

- [ ] Service is running: `sudo systemctl is-active musohu-web`
- [ ] Auto-start enabled: `sudo systemctl is-enabled musohu-web`
- [ ] Health responds: `curl http://localhost/api/health`
- [ ] Web UI accessible: Open http://localhost in browser
- [ ] Logs visible: `sudo journalctl -u musohu-web -n 10`
- [ ] Tests pass: `bash scripts/test/test_production_setup.sh`
- [ ] Port 80 listening: `sudo ss -tuln | grep :80`

---

**Created**: November 12, 2025  
**Version**: 1.0
