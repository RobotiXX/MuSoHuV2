#!/bin/bash

#***********************************************************************
# Configure DNS for Hotspot
#***********************************************************************
# This script configures DNS for hotspot hostname resolution
# It installs and configures dnsmasq to provide DNS services for the
# hotspot network, enabling hostname-based access (robotixx/robotixx.local)
#***********************************************************************

#***********************************************************************
# Help function
#***********************************************************************

show_help() {
    cat << EOF
Usage: sudo bash configure-dns.sh [OPTIONS]

Configure DNS for the Robotixx MuSoHu hotspot network.

This script:
  - Installs dnsmasq if not already installed
  - Configures DHCP and DNS services for the hotspot
  - Enables hostname-based access (robotixx/robotixx.local)
  - Sets up DNS forwarding to Google DNS servers

Network Configuration:
  Interface:     wlP1p1s0
  DHCP Range:    10.42.0.10 - 10.42.0.100
  Gateway:       10.42.0.1
  DNS Servers:   8.8.8.8, 8.8.4.4

Options:
  -h, --help     Display this help message and exit

Examples:
  sudo bash configure-dns.sh
  sudo bash configure-dns.sh --help

Note: This script requires root privileges to configure system services.

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
    shift
done

# Get script directory and source utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(dirname "$SCRIPT_DIR")/utils/logging_config.sh"

log_info "Starting DNS configuration for hotspot..."
log_separator

#***********************************************************************
# Install dnsmasq package
#***********************************************************************

# Install dnsmasq if not already installed
if ! command -v dnsmasq &> /dev/null; then
    log_info "Installing dnsmasq..."
    sudo apt-get update
    sudo apt-get install -y dnsmasq

    if [ $? -eq 0 ]; then
        log_success "dnsmasq installed successfully"
    else
        log_error "Failed to install dnsmasq"
        exit 1
    fi
else
    log_info "dnsmasq is already installed"
fi

#***********************************************************************
# Configure dnsmasq for hotspot
#***********************************************************************

# Stop dnsmasq service temporarily
log_info "Stopping dnsmasq service..."
sudo systemctl stop dnsmasq

# Backup original dnsmasq configuration
log_info "Backing up original dnsmasq configuration..."
sudo cp /etc/dnsmasq.conf /etc/dnsmasq.conf.backup 2>/dev/null || true

# Create dnsmasq.d directory if it doesn't exist
sudo mkdir -p /etc/dnsmasq.d

# Create hotspot-specific dnsmasq configuration
log_info "Creating hotspot DNS configuration..."
sudo tee /etc/dnsmasq.d/hotspot.conf > /dev/null <<EOF
# Hotspot DNS Configuration for Robotixx MuSoHu
# Interface to bind dnsmasq to
interface=wlP1p1s0

# DHCP range and lease time (12 hours)
dhcp-range=10.42.0.10,10.42.0.100,255.255.255.0,12h

# DHCP options: 3=router, 6=DNS server
dhcp-option=3,10.42.0.1
dhcp-option=6,10.42.0.1

# Upstream DNS servers (Google DNS)
server=8.8.8.8
server=8.8.4.4

# Local DNS records for hostname resolution
address=/robotixx/10.42.0.1
address=/robotixx.local/10.42.0.1
EOF

if [ $? -eq 0 ]; then
    log_success "DNS configuration file created successfully"
else
    log_error "Failed to create DNS configuration file"
    exit 1
fi

#***********************************************************************
# Enable and start dnsmasq service
#***********************************************************************

log_info "Enabling dnsmasq service..."
sudo systemctl enable dnsmasq

log_info "Restarting dnsmasq service..."
sudo systemctl restart dnsmasq

if [ $? -eq 0 ]; then
    log_success "dnsmasq service started successfully"
else
    log_error "Failed to start dnsmasq service"
    exit 1
fi

#***********************************************************************
# Configuration complete
#***********************************************************************

log_separator
log_success "DNS configuration completed successfully"
log_separator

log_info "Devices connected to hotspot can now access services using:"
log_info ""
log_info "  Hostname-based URLs:"
log_info "    - http://robotixx:6080 (ROS2 VNC)"
log_info "    - http://robotixx:8000 (Web App)"
log_info ""
log_info "  IP-based URLs (alternative):"
log_info "    - http://10.42.0.1:6080 (ROS2 VNC)"
log_info "    - http://10.42.0.1:8000 (Web App)"
