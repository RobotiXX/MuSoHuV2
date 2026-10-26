// Copyright 2026 nle
// Licensed under the Apache License, Version 2.0

#include <memory>

#include "rclcpp/rclcpp.hpp"
#include "musohu_bag_recorder/bag_recorder_node.hpp"

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<musohu_bag_recorder::BagRecorderNode>());
  rclcpp::shutdown();
  return 0;
}

