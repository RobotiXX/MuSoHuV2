# MuSoHu Scripts Directory Guide

This directory contains all shell scripts for the MuSoHu project, organized by category and following standardized coding conventions.

**Last Updated**: November 2025

---

## Table of Contents

1. [Directory Structure](#directory-structure)
2. [Script Categories](#script-categories)
3. [Coding Standards](#coding-standards)
4. [Usage Examples](#usage-examples)
5. [Logging System](#logging-system)
6. [Adding New Scripts](#adding-new-scripts)
7. [Verification](#verification)

---

## Directory Structure

```
scripts/
├── setup/              # Installation and setup scripts
│   ├── install_zed_sdk.sh
│   ├── install_python_packages.sh
│   ├── install_ufw.sh
│   ├── troubleshoot_ch340_driver.sh
│   ├── download_driver_ros2.sh
│   ├── setup_web_service.sh
│   ├── setup_production_web_service.sh
│   └── test_production_setup.sh
├── utils/              # Utility scripts and helpers
│   ├── logging_config.sh
│   ├── detect_system_info.sh
│   ├── manage_web_service.sh
│   ├── test_system_detection.sh
│   └── example_with_logging.sh
├── hotspot/            # WiFi hotspot configuration
│   ├── start-hotspot.sh
│   ├── configure-dns.sh
│   ├── setup-hotspot-dns.sh
│   └── setup-hotspot-service.sh
├── udev_rules/         # Device configuration
│   ├── setup_udev.sh
│   └── rules/
│       ├── 40-respeaker.rules
│       ├── 40-zed.rules
│       └── 99-imu.rules
├── logs/               # Log files (auto-generated, gitignored)
├── SCRIPTS_GUIDE.md    # This file
├── SCRIPT_STANDARDS.md # Detailed coding standards
├── ENHANCEMENT_SUMMARY.md # Enhancement documentation
└── verify_standards.sh # Standards verification tool
```

---

## Script Categories

### Setup Scripts (`setup/`)

Installation and configuration scripts for system components:

- **install_zed_sdk.sh** - Install ZED SDK for camera support
- **install_python_packages.sh** - Install Python dependencies
- **install_ufw.sh** - Configure UFW firewall
- **troubleshoot_ch340_driver.sh** - Fix CH340 USB-to-serial driver issues
- **download_driver_ros2.sh** - Download ROS2 sensor drivers
- **setup_web_service.sh** - Setup Flask web service
- **setup_production_web_service.sh** - Production web service setup
- **test_production_setup.sh** - Verify production setup

### Utility Scripts (`utils/`)

Reusable utilities and helper scripts:

- **logging_config.sh** - Centralized logging system
- **detect_system_info.sh** - Detect Ubuntu and CUDA versions
- **manage_web_service.sh** - Web service management commands
- **test_system_detection.sh** - Test system detection
- **example_with_logging.sh** - Logging usage example

### Hotspot Scripts (`hotspot/`)

WiFi hotspot configuration and management:

- **start-hotspot.sh** - Start the Robotixx MuSoHu hotspot
- **configure-dns.sh** - Configure DNS for hotspot
- **setup-hotspot-dns.sh** - Complete DNS setup
- **setup-hotspot-service.sh** - Install systemd service for hotspot

### Device Configuration (`udev_rules/`)

USB device configuration and udev rules:

- **setup_udev.sh** - Install udev rules for all devices
- **rules/** - Device-specific udev rule files

---

## Coding Standards

All scripts in this directory follow the **MuSoHu Script Standards**. See `SCRIPT_STANDARDS.md` for complete documentation.

### Key Standards

#### 1. Structured Commenting

Every script uses `#***********************************************************************` style headers:

```bash
#!/bin/bash

#***********************************************************************
# Script Title
#***********************************************************************
# Description:
#   Clear explanation of script purpose
#
# Usage:
#   ./script.sh [OPTIONS]
#
# Options:
#   -h, --help    Show help
#
# Author: MuSoHu Team
# Date: November 2025
#***********************************************************************
```

#### 2. Comprehensive Help

All scripts support `-h` and `--help` with detailed help text:

```bash
./any_script.sh --help
```

#### 3. Centralized Logging

All scripts use the logging system:

```bash
source "$SCRIPT_DIR/../utils/logging_config.sh"
log_info "Message"
log_success "Success!"
log_error "Error occurred"
```

#### 4. Section Organization

Scripts are organized with clear section markers:

```bash
#***********************************************************************
# Configuration and Initialization
#***********************************************************************

#***********************************************************************
# Helper Functions
#***********************************************************************

#***********************************************************************
# Main Execution
#***********************************************************************
```

---

## Usage Examples

### Getting Help

Every script provides comprehensive help:

```bash
# Any of these work
./script.sh -h
./script.sh --help
```

### Running with Debug Mode

Enable detailed logging:

```bash
# Method 1: Environment variable
export DEBUG_ENABLED=true
./script.sh

# Method 2: Command-line option (if supported)
./script.sh --debug
```

### Viewing Logs

All scripts generate log files:

```bash
# View recent logs
tail -f scripts/logs/script_name_*.log

# Search for errors
grep ERROR scripts/logs/*.log

# View specific script logs
ls -lt scripts/logs/script_name_*.log | head -5
```

### Common Script Patterns

#### Setup Scripts

```bash
# Install ZED SDK
sudo bash scripts/install/install_zed_sdk.sh

# Setup production web service
bash scripts/deploy/setup_production_web_service.sh
```

#### Utility Scripts

```bash
# Detect system information
bash scripts/utils/detect_system_info.sh

# Manage web service
sudo bash scripts/utils/manage_web_service.sh start
```

#### Hotspot Scripts

```bash
# Start hotspot
sudo bash scripts/hotspot/start-hotspot.sh

# Install/enable at boot without switching the current Wi-Fi connection
./scripts/hotspot/setup-hotspot-service.sh
```

Open http://10.42.0.1:8000/ on the hotspot. NetworkManager shared mode provides
DHCP/DNS; the separate legacy dnsmasq setup is not needed for this workflow.

---

## Logging System

### Overview

The centralized logging system (`utils/logging_config.sh`) provides:
- Color-coded output
- Automatic log file generation
- Debug mode control
- Dual output (console and file)

### Usage in Scripts

```bash
#!/bin/bash

# Source logging configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../utils/logging_config.sh"

# Use logging functions
log_info "Starting process..."
log_debug "Debug information"
log_success "Process completed successfully"
log_warning "Non-critical warning"
log_error "Critical error occurred"
log_separator  # Visual separator
```

### Log Levels

- **log_debug** - Debug-level details (only shown if `DEBUG_ENABLED=true`)
- **log_info** - General information (blue)
- **log_success** - Success messages (green)
- **log_warning** - Non-critical issues (yellow)
- **log_error** - Critical failures (red)
- **log_separator** - Visual separator line

### Log Files

- **Location**: `scripts/logs/`
- **Format**: `script_name_YYYYMMDD_HHMMSS.log`
- **Retention**: Managed manually (not auto-deleted)

---

## Adding New Scripts

### Quick Start

1. **Use the template** from `SCRIPT_STANDARDS.md`
2. **Place in appropriate directory** (setup/, utils/, hotspot/, etc.)
3. **Make executable**: `chmod +x script_name.sh`
4. **Test help function**: `./script_name.sh --help`
5. **Verify standards**: `bash scripts/verify_standards.sh`
6. **Update this guide** with script description

### Checklist for New Scripts

- [ ] Structured header comment with `#***********************************************************************`
- [ ] Comprehensive `show_help()` function
- [ ] Support for `-h` and `--help` options
- [ ] Clear section markers
- [ ] Centralized logging usage
- [ ] Command-line argument parsing
- [ ] Error handling for critical operations
- [ ] Usage examples in help text
- [ ] Documentation in SCRIPTS_GUIDE.md
- [ ] Passes `verify_standards.sh` checks

### Template

See `SCRIPT_STANDARDS.md` section "Standard Script Template" for a complete starting template.

---

## Verification

### Verify Script Standards

Use the verification tool to check compliance:

```bash
# Check all scripts
bash scripts/verify_standards.sh

# Detailed output
bash scripts/verify_standards.sh --verbose

# Only show summary
bash scripts/verify_standards.sh --quiet
```

### Manual Verification

Check individual aspects:

```bash
# Check for structured headers
grep -l "^#\*\*\*\*\*\*\*" scripts/**/*.sh

# Check for help functions
grep -l "show_help()" scripts/**/*.sh

# Check for logging usage
grep -l "log_info\|log_success" scripts/**/*.sh

# Test help functionality
for script in scripts/**/*.sh; do
    echo "Testing: $script"
    bash "$script" --help > /dev/null 2>&1 && echo "✅" || echo "❌"
done
```

---

## Best Practices

### 1. Always Provide Help

Every script should be self-documenting:

```bash
show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Complete help text with:
- Description
- All options
- Examples
- Prerequisites
EOF
}
```

### 2. Use Structured Comments

Organize code with clear section markers:

```bash
#***********************************************************************
# Major Section Name
#***********************************************************************

#######################################################################
# Subsection if needed
#######################################################################
```

### 3. Proper Error Handling

Check critical operations:

```bash
if command; then
    log_success "Command succeeded"
else
    log_error "Command failed"
    exit 1
fi
```

### 4. Check Prerequisites

Verify requirements before proceeding:

```bash
# Check for sudo
if [ "$EUID" -ne 0 ]; then
    log_error "This script requires sudo"
    exit 1
fi

# Check for required commands
if ! command -v required_tool &> /dev/null; then
    log_error "required_tool not found"
    exit 1
fi
```

### 5. Provide Examples

Include practical examples in help text:

```bash
EXAMPLES:
    # Basic usage
    $(basename "$0") input.txt
    
    # With debug mode
    $(basename "$0") --debug input.txt
```

---

## Troubleshooting

### Common Issues

**Issue**: Script not executable
```bash
chmod +x script_name.sh
```

**Issue**: Logging not working
```bash
# Verify logging_config.sh is sourced
grep "source.*logging_config.sh" script_name.sh

# Check path is correct
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
```

**Issue**: Help not displaying
```bash
# Verify help function exists
grep -A5 "show_help()" script_name.sh

# Check argument parsing
grep "\-h|\-\-help" script_name.sh
```

---

## Additional Resources

- **SCRIPT_STANDARDS.md** - Complete coding standards
- **ENHANCEMENT_SUMMARY.md** - Enhancement documentation
- **verify_standards.sh** - Automated verification tool
- **utils/logging_config.sh** - Logging system documentation
- **utils/example_with_logging.sh** - Logging example

---

## Quick Reference

### Common Commands

```bash
# Get help for any script
./script.sh --help

# Enable debug mode
export DEBUG_ENABLED=true
./script.sh

# View logs
tail -f scripts/logs/script_name_*.log

# Verify standards
bash scripts/verify_standards.sh

# Make script executable
chmod +x script_name.sh
```

### File Locations

- Scripts: `scripts/{setup,utils,hotspot,udev_rules}/`
- Logs: `scripts/logs/`
- Standards: `scripts/SCRIPT_STANDARDS.md`
- This guide: `scripts/SCRIPTS_GUIDE.md`

---

For questions or issues, refer to the project documentation or contact the team.
