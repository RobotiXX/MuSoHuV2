# Web service deployment

Run these commands from the repository root **as the normal user**:

```bash
./scripts/deploy/setup_production_web_service.sh --prepare-only
```

This creates/reuses `web-app/venv`, installs Python requirements, renders
`web-app/deploy/musohu-web.service` and checks it with systemd. It does not
install or restart the running service. Build `musohu_ws` first; the installer
requires its Humble overlay. Use `--port 8001` to render an alternate port.

Installation also runs `scripts/setup/setup_time_sync_permissions.sh` for
narrow date/set-ntp permissions; the new unit permits those sudo commands to
elevate. For a manual preview, run that permissions helper separately first. The optional `--with-power-modes` is for Jetson power
benchmarks and is not required for the web app.

Review the generated unit, then migrate when ready:

```bash
./scripts/deploy/setup_production_web_service.sh --install --port 8000
```

Only installation/service management uses sudo. This replaces, enables and
restarts `musohu-web.service` and checks its HTTP health endpoint. It does not
change WiFi, hotspot, DNS or firewall settings. The old service currently
runs from `~/git/MuSoHu`; preparation alone preserves it.

The service uses one Uvicorn worker and this checkout's ROS workspace. Its
memory limits account for ROS children, and SIGINT/shutdown timeouts allow
bag flushing. Review those limits for sustained workloads on an 8 GB Nano.

```bash
systemctl status musohu-web.service
journalctl -u musohu-web.service -n 100 --no-pager
sudo systemctl restart musohu-web.service
```

For a temporary preview and hardware-independent recording development, see
[web-app/README.md](../../web-app/README.md). Do not start two applications
controlling the same hardware simultaneously.
