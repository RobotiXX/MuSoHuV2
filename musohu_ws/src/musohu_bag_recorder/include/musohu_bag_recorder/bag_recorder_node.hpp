// Copyright 2026 nle
// Licensed under the Apache License, Version 2.0
// Adapted for MuSoHu; see UPSTREAM.md.
#pragma once
#include <chrono>
#include <filesystem>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/generic_subscription.hpp>
#include <rosbag2_cpp/writer.hpp>
#include <std_msgs/msg/string.hpp>
#include "musohu_bag_recorder/srv/trigger_bag_recording.hpp"
#include "musohu_bag_recorder/srv/stop_bag_recording.hpp"
#include "musohu_bag_recorder/srv/get_bag_recording_state.hpp"

namespace musohu_bag_recorder {
class BagRecorderNode : public rclcpp::Node {
public:
  using TriggerRecording = srv::TriggerBagRecording;
  using StopRecording = srv::StopBagRecording;
  using RecordingState = srv::GetBagRecordingState;
  explicit BagRecorderNode(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());
  ~BagRecorderNode() override;
private:
  void triggerRecording(const std::shared_ptr<TriggerRecording::Request>,
                        std::shared_ptr<TriggerRecording::Response>);
  void stopRecording(const std::shared_ptr<StopRecording::Request>,
                     std::shared_ptr<StopRecording::Response>);
  void discoverTopics();
  void subscribeTopic(const std::string &, const std::string &);
  void finishRecording(const std::string &, bool failed = false);
  nlohmann::json state() const;
  void writeMetadata() const;
  void publishState();
  static std::filesystem::path expandUserPath(const std::string &);
  static std::string timestampUtc();
  mutable std::recursive_mutex mutex_;
  rclcpp::Clock host_clock_{RCL_SYSTEM_TIME};
  std::filesystem::path output_directory_, active_bag_uri_;
  std::string config_file_, active_session_id_, status_{"stopped"}, error_;
  std::string started_at_utc_, finished_at_utc_, finish_reason_;
  nlohmann::json settings_, context_;
  std::vector<std::string> configured_topics_;
  std::set<std::string> trigger_reasons_;
  std::map<std::string, uint64_t> counts_;
  std::map<std::string, std::shared_ptr<rclcpp::GenericSubscription>> subscriptions_;
  std::unique_ptr<rosbag2_cpp::Writer> writer_;
  bool recording_{false}, finalized_{false};
  double owner_timeout_sec_{0};
  uint64_t status_ticks_{0};
  std::chrono::steady_clock::time_point last_owner_contact_;
  rclcpp::Service<TriggerRecording>::SharedPtr trigger_service_;
  rclcpp::Service<StopRecording>::SharedPtr stop_service_;
  rclcpp::Service<RecordingState>::SharedPtr state_service_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr state_publisher_;
  rclcpp::TimerBase::SharedPtr discovery_timer_;
};
}  // namespace musohu_bag_recorder

