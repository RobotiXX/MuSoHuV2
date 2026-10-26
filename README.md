# MuSoHu: Multi-Modal Social Human Navigation (v2)
Last updated: 2026-10-26

Multi-Modal Social Human Navigation Dataset - A robotics research platform developed at George Mason University for collecting data on human-robot interactions in social navigation contexts.

**Project Website:** [https://cs.gmu.edu/~xiao/Research/MuSoHu/](https://cs.gmu.edu/~xiao/Research/MuSoHu/)

## About

This project collects social human navigation data in natural human-inhabited public spaces. An egocentric data collection sensor suite worn by walking humans captures multi-modal robot perception data.

### Dataset Scale
- **~100 km** of navigation data
- **20 hours** of recording
- **300 trials** across various environments
- **13 human** participants
- Multiple public spaces with natural social navigation interactions

## Multi-Modal Sensor Suite

The wearable data collection device includes:

- **3D LiDAR** - Robosense Helios 32 (360° environmental scanning)
- **Stereo Camera** - Stereolabs ZED 2i (record colour stereo for offline depth)
- **IMU** - Inertial Measurement Unit (motion tracking)
- **Odometry** - ZED visual-inertial pose and motion tracking
- **Microphone Array** - Seeed Studio ReSpeaker Mic Array (spatial audio capture)

## Documentation

For complete documentation, setup instructions, and production deployment guides, see:

- **[ROS 2 workspace](musohu_ws/README.md)** - Sensor sources, SDK setup, build, bringup and evaluation recording
- **[Current work plan](TODO.md)** - Agreed ROS, odometry/IMU, recording and mechanical tasks
- **[Contributor instructions](AGENTS.md)** - Project context and working conventions
- **[Session clocks](musohu_ws/README.md#session-clocks)** - Offline phone/online NTP and LiDAR PTP
- **[Stereo capture](musohu_ws/README.md#sensors-and-stereo-recording)** - Nominal packed images, calibration and offline depth
- **[Web recording](web-app/README.md)** - Recording presets, session metadata and dummy publishers
- **[Service deployment](scripts/deploy/README.md)** - Prepare and migrate the systemd service

## Overview

MuSoHu is a platform for collecting data for social navigation research. It is built using ROS2 and includes a web interface for system interaction.

### Features
- ROS2-based robotics platform
- Multi-sensor integration (ZED camera, LiDAR, IMU, Audio)
- Web interface for system control and monitoring
- Deployment with automatic restart capability
- Helmet-mounted sensor suite for data collection

### Project Structure
- `musohu_ws/` - ROS 2 Humble workspace with pinned sensor dependencies
  - `src/helmet_bringup/` - Project launch files and sensor configurations
  - `scripts/` - Dependency/SDK setup, symlink build, validation and recording helpers
- `web-app/` - FastAPI/Uvicorn web interface for system control
- `scripts/` - Setup, installation, and utility scripts
  - `setup/` - Installation and configuration scripts
  - `utils/` - Helper utilities and logging
  - `udev_rules/` - Device access rules for sensors
  - `hotspot/` - WiFi hotspot configuration
- `docs/` - Complete documentation and guides
