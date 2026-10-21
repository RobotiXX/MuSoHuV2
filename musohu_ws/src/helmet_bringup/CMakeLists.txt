cmake_minimum_required(VERSION 3.8)
project(helmet_bringup)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)

# Keep ROS DDS discovery and traffic on this host when sourcing the workspace.
ament_environment_hooks("env-hooks/ros_localhost_only.dsv.in")

# Install launch files
install(DIRECTORY
  launch
  config
  DESTINATION share/${PROJECT_NAME}
)

install(PROGRAMS
  scripts/action_generator.py
  scripts/check_lidar_clock.py
  scripts/clock_reference.py
  scripts/time_sync_monitor.py
  scripts/sensor_health_monitor.py
  scripts/sensor_health_model.py
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
