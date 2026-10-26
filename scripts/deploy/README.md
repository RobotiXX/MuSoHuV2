# Web service deployment

Run these commands from the repository root **as the normal user**:

```bash
./scripts/deploy/setup_production_web_service.sh --prepare-only
```

This creates/reuses `web-app/venv`, installs Python requirements, renders
`web-app/deploy/musohu-web.service` and checks it with systemd. It does not
install or restart the running service. Build `musohu_ws` first; the installer
requires its Humble overlay. Use `--port 8001` to render an alternate port.
The API venv excludes system/user packages; ROS children use system Python
with the workspace overlay separately.

Installation installs the pinned MCAP CLI and enables `musohu-zenoh.service`
(loopback only), which the web unit requires and starts after. The web service
selects `rmw_zenoh_cpp`; ROS children receive the tuned workspace environment.
The router installer starts idempotently and does not restart an active router.

Installation also runs `scripts/setup/setup_time_sync_permissions.sh` for
narrow date/set-ntp permissions; the new unit permits those sudo commands to
elevate. For a manual preview, run that permissions helper separately first.
The optional `--with-power-modes` allows explicit Jetson power-mode changes;
it is not required for the nominal web workflow.

Review the generated unit, then migrate when ready:

```bash
./scripts/deploy/setup_production_web_service.sh --install --port 8000
```

Only installation/service management uses sudo. This replaces, enables and
restarts `musohu-web.service` and checks its HTTP health endpoint. It does not
change WiFi, hotspot, DNS or firewall settings. Stop recording and sensor
launches before installation. Preparation alone preserves the running unit.

As of 2026-10-21, this Jetson's production service runs from
`/home/jetson/repos/MuSoHuV2` on port 8000. The previous `~/git/MuSoHu`
checkout was archived with its local edits/logs and removed. Migration backups
are under `~/.local/state/musohu/migrations/`. Existing `~/helmet_bags` and the
reference `~/ros2_musohu_ws` remain in place.

On the helmet hotspot, use **http://10.42.0.1:8000/**; on another network use
the Jetson's current address with port 8000. The HTTP listener binds to all
interfaces; ROS remains localhost-only. To install the hotspot boot unit for
this checkout without switching the current Wi-Fi connection:

```bash
./scripts/hotspot/setup-hotspot-service.sh
```

That installer renders the absolute script path and enables the boot service;
it does not activate the hotspot. The start script pins `10.42.0.1/24` and
uses NetworkManager shared mode for DHCP/DNS. A separate dnsmasq DHCP service
is not required. Activate the hotspot only when ready to disconnect lab Wi-Fi:

```bash
sudo systemctl restart hotspot.service
```

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
