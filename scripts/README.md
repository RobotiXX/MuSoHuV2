# MuSoHu Scripts

This directory contains all scripts for setting up, deploying, managing, and testing the MuSoHu system.

## Directory Structure

```
scripts/
├── setup/            # Legacy installer artifact (not the workspace setup)
├── deploy/           # Deployment and service setup scripts
├── test/             # Testing and verification scripts
├── utils/            # Utility and management scripts
├── hotspot/          # WiFi hotspot configuration
├── udev_rules/       # Device rules setup
└── logs/             # Script execution logs (not in version control)
```

## Quick Start

### 1. Install Dependencies

```bash
# Run as your normal user in a fresh terminal; sudo is used for dependencies.
./musohu_ws/scripts/setup.sh
# Install only, or rebuild without sudo:
./musohu_ws/scripts/setup.sh --deps-only
./musohu_ws/scripts/setup.sh --build-only
```

### 2. Deploy Production Service

```bash
./scripts/deploy/setup_production_web_service.sh --prepare-only
# After reviewing web-app/deploy/musohu-web.service:
./scripts/deploy/setup_production_web_service.sh --install
```

### 3. Verify Setup

```bash
bash scripts/test/test_production_setup.sh
```

### 4. Manage Service

```bash
# Check status
bash scripts/utils/manage_web_service.sh status

# View logs
bash scripts/utils/manage_web_service.sh logs

# Restart service
sudo bash scripts/utils/manage_web_service.sh restart
```

## Documentation

For detailed documentation, see:
- [Installation Summary](../docs/guides/INSTALLATION_SUMMARY.md)
- [Production Setup Guide](../docs/guides/PRODUCTION_SETUP.md)
- [Production Web Service Guide](../docs/guides/PRODUCTION_WEB_SERVICE.md)
- [Scripts Guide](../docs/guides/SCRIPTS_GUIDE.md)
- [Quick Reference](../docs/reference/QUICK_REFERENCE.md)

## Script Organization

### ROS workspace setup (`../musohu_ws/scripts/`)
`setup.sh` installs native/ROS/Python dependencies and SDK 5.5 if missing,
then builds with `--symlink-install`. It replaces the nonexistent older
`scripts/install/` commands. `zed-sdk.sh` can download/install the SDK alone;
`validate-sensors.py` observes a running rig and saves acquisition statistics.
See [workspace operation](../musohu_ws/README.md).

### Deployment (`deploy/`)
Production deployment and service setup. See [deploy/README.md](deploy/README.md).

### Testing (`test/`)
Verification and testing scripts. See [test/README.md](test/README.md).

### Utilities (`utils/`)
Management and helper utilities:
- `manage_web_service.sh` - Service management
- `detect_system_info.sh` - System information detection
- `logging_config.sh` - Shared logging functions

### Hotspot (`hotspot/`)
WiFi hotspot setup and configuration.

### UDEV Rules (`udev_rules/`)
Device rules for hardware permissions.

## Logging

All scripts use a standardized logging system defined in `utils/logging_config.sh`. Logs are saved to `scripts/logs/` (excluded from version control).

## Contributing

When adding new scripts:
1. Follow the [Script Standards](../docs/standards/SCRIPT_STANDARDS.md)
2. Include proper help text and documentation
3. Use the logging system from `utils/logging_config.sh`
4. Place in the appropriate directory based on purpose
5. Update this README and relevant documentation
