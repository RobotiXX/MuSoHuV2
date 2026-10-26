# Source provenance

Adapted, at the maintainer's explicit request, from RobotiXX/ScoutMini,
branch `nle/refactor-rwd-ws`, commit `d215ec31c7dc2bef5cd899df6ef259929ec1fff4`,
directory `rwd_ws/src/rwd_bag_recorder`.

Upstream: https://github.com/RobotiXX/ScoutMini/tree/d215ec31c7dc2bef5cd899df6ef259929ec1fff4/rwd_ws/src/rwd_bag_recorder

Original copyright: 2026 nle. License: Apache-2.0.
This MuSoHu adaptation retains the C++ serialized-subscription/rosbag2 writer
design and service lifecycle. Navigation task/map/semantic dependencies are
replaced with MuSoHu session ownership, per-session topics/settings, confirmed
readiness/finalization and provenance supplied by the web service client.
