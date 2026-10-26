// Copyright 2026 nle
// Licensed under the Apache License, Version 2.0
// MuSoHu adaptation of ScoutMini's serialized-message recorder; see UPSTREAM.md.
#include "musohu_bag_recorder/bag_recorder_node.hpp"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <regex>
#include <sstream>
#include <unistd.h>
#include <yaml-cpp/yaml.h>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <rmw/rmw.h>
#include <rosbag2_transport/qos.hpp>
#include <rosbag2_compression/sequential_compression_writer.hpp>

namespace musohu_bag_recorder {
namespace {
using Json = nlohmann::json;
Json readSettings(const std::string & path, const std::string & overrides) {
  Json settings = {{"storage", "mcap"}, {"serialization_format", ""},
    {"max_cache_size", 104857600}, {"compression_mode", "none"},
    {"compression_format", "zstd"}, {"compression_queue_size", 1},
    {"compression_threads", 0}};
  Json supplied = Json::object();
  if (!overrides.empty()) {
    supplied = Json::parse(overrides);
  } else if (!path.empty()) {
    const auto yaml = YAML::LoadFile(path);
    if (!yaml.IsMap()) {throw std::invalid_argument("Recorder config must be a mapping");}
    for (const auto & item : yaml) {
      const auto key = item.first.as<std::string>();
      if (!settings.contains(key)) {throw std::invalid_argument("Unknown recorder setting: " + key);}
      if (settings[key].is_number_integer()) {supplied[key] = item.second.as<int64_t>();}
      else {supplied[key] = item.second.as<std::string>();}
    }
  }
  if (!supplied.is_object()) {throw std::invalid_argument("settings_json must be an object");}
  for (auto item = supplied.begin(); item != supplied.end(); ++item) {
    if (!settings.contains(item.key())) {throw std::invalid_argument("Unknown recorder setting: " + item.key());}
    if (settings[item.key()].is_number_integer()) {
      if (!item.value().is_number_integer() ||
        (item.value().is_number_integer() && !item.value().is_number_unsigned() && item.value().get<int64_t>() < 0))
      {throw std::invalid_argument(item.key() + " must be a nonnegative integer");}
    } else if (!item.value().is_string()) {
      throw std::invalid_argument(item.key() + " must be a string");
    }
    settings[item.key()] = item.value();
  }
  static const std::regex identifier("[A-Za-z0-9_][A-Za-z0-9_.-]*");
  for (const auto & key : {"storage", "serialization_format", "compression_format"}) {
    const auto value = settings[key].get<std::string>();
    if (!(std::regex_match(value, identifier) || (value.empty() && std::string(key) != "storage"))) {
      throw std::invalid_argument(std::string("Invalid recorder ") + key);
    }
  }
  const auto mode = settings["compression_mode"].get<std::string>();
  if (mode != "none" && mode != "file" && mode != "message") {
    throw std::invalid_argument("compression_mode must be none, file or message");
  }
  if (mode != "none" && settings["compression_format"] == "") {
    throw std::invalid_argument("compression_format is required");
  }
  if (settings["storage"] == "mcap" && mode == "message") {
    throw std::invalid_argument("MCAP does not support rosbag2 message compression");
  }
  return settings;
}
}  // namespace

BagRecorderNode::BagRecorderNode(const rclcpp::NodeOptions & options)
: Node("musohu_bag_recorder", options) {
  output_directory_ = std::filesystem::weakly_canonical(expandUserPath(
    declare_parameter<std::string>("output_directory", "~/helmet_bags")));
  config_file_ = declare_parameter<std::string>("config_file",
    ament_index_cpp::get_package_share_directory("musohu_bag_recorder") + "/config/bag_recorder_config.yml");
  const auto discovery_ms = declare_parameter<int>("topic_discovery_period_ms", 250);
  if (discovery_ms <= 0) {throw std::invalid_argument("topic_discovery_period_ms must be positive");}
  state_publisher_ = create_publisher<std_msgs::msg::String>(
    "/musohu/recorder/state", rclcpp::QoS(1).reliable().transient_local());
  trigger_service_ = create_service<TriggerRecording>("/musohu/recorder/start",
    std::bind(&BagRecorderNode::triggerRecording, this, std::placeholders::_1, std::placeholders::_2));
  stop_service_ = create_service<StopRecording>("/musohu/recorder/stop",
    std::bind(&BagRecorderNode::stopRecording, this, std::placeholders::_1, std::placeholders::_2));
  state_service_ = create_service<RecordingState>("/musohu/recorder/get_state",
    [this](const std::shared_ptr<RecordingState::Request> request,
           std::shared_ptr<RecordingState::Response> response) {
      std::lock_guard<std::recursive_mutex> lock(mutex_);
      if (recording_ && request->renew_lease && request->session_id == active_session_id_) {
        last_owner_contact_ = std::chrono::steady_clock::now();
      }
      response->state_json = state().dump();
    });
  discovery_timer_ = create_wall_timer(std::chrono::milliseconds(discovery_ms), [this, discovery_ms]() {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    try {
      if (recording_ && owner_timeout_sec_ > 0 &&
        std::chrono::duration<double>(std::chrono::steady_clock::now() - last_owner_contact_).count() > owner_timeout_sec_)
      {
        error_ = "Recording owner stopped renewing its lease";
        finishRecording("owner_lease_expired", true);
      } else {discoverTopics();}
    } catch (const std::exception & error) {
      error_ = error.what();
      finishRecording("discovery_error", true);
    }
    // State is small and only emitted at roughly 1 Hz, independent of sensor rates.
    if (++status_ticks_ % std::max<int64_t>(1, 1000 / discovery_ms) == 0) {publishState();}
  });
  publishState();
  RCLCPP_INFO(get_logger(), "Recorder services ready; output=%s", output_directory_.c_str());
}

BagRecorderNode::~BagRecorderNode() {
  std::lock_guard<std::recursive_mutex> lock(mutex_);
  if (recording_) {finishRecording("node_shutdown");}
}

void BagRecorderNode::triggerRecording(
  const std::shared_ptr<TriggerRecording::Request> request,
  std::shared_ptr<TriggerRecording::Response> response) {
  std::lock_guard<std::recursive_mutex> lock(mutex_);
  try {
    static const std::regex session_pattern("[A-Za-z0-9_-]{1,160}");
    static const std::regex topic_pattern("/[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*");
    if (!std::regex_match(request->session_id, session_pattern)) {
      throw std::invalid_argument("Invalid session_id");
    }
    if (recording_) {
      if (request->session_id != active_session_id_) {
        throw std::runtime_error("Another session already owns the active recording");
      }
      last_owner_contact_ = std::chrono::steady_clock::now();
      trigger_reasons_.insert(request->reason);
      writeMetadata();
      response->success = true;
      response->message = "Session already recording; no new bag created";
    } else {
      auto topics = request->topics;
      if (topics.empty() || topics.size() > 256) {throw std::invalid_argument("Select 1-256 absolute topics");}
      for (const auto & topic : topics) {
        if (topic.size() > 255 || !std::regex_match(topic, topic_pattern)) {
          throw std::invalid_argument("Invalid topic: " + topic);
        }
      }
      std::sort(topics.begin(), topics.end());
      topics.erase(std::unique(topics.begin(), topics.end()), topics.end());
      if (!std::isfinite(request->owner_timeout_sec) || request->owner_timeout_sec < 0) {
        throw std::invalid_argument("Invalid owner timeout");
      }
      const auto settings = readSettings(config_file_, request->settings_json);
      const auto context = request->context_json.empty() ? Json::object() : Json::parse(request->context_json);
      if (!context.is_object()) {throw std::invalid_argument("context_json must be an object");}
      const auto uri = std::filesystem::weakly_canonical(request->bag_uri.empty() ?
        output_directory_ / request->session_id : std::filesystem::path(request->bag_uri));
      const auto relative = uri.lexically_relative(output_directory_);
      if (!uri.is_absolute() || relative.empty() || *relative.begin() == ".." || relative == ".") {
        throw std::invalid_argument("bag_uri must be inside output_directory");
      }
      if (std::filesystem::exists(uri)) {throw std::invalid_argument("Bag path already exists; refusing overwrite");}
      std::filesystem::create_directories(uri.parent_path());
      std::unique_ptr<rosbag2_cpp::Writer> writer;
      const auto mode = settings["compression_mode"].get<std::string>();
      if (mode == "none") {writer = std::make_unique<rosbag2_cpp::Writer>();}
      else {
        rosbag2_compression::CompressionOptions compression;
        compression.compression_format = settings["compression_format"].get<std::string>();
        compression.compression_mode = rosbag2_compression::compression_mode_from_string(mode);
        compression.compression_queue_size = settings["compression_queue_size"].get<uint64_t>();
        compression.compression_threads = settings["compression_threads"].get<uint64_t>();
        writer = std::make_unique<rosbag2_cpp::Writer>(
          std::make_unique<rosbag2_compression::SequentialCompressionWriter>(compression));
      }
      rosbag2_storage::StorageOptions storage;
      storage.uri = uri.string();
      storage.storage_id = settings["storage"].get<std::string>();
      storage.max_cache_size = settings["max_cache_size"].get<uint64_t>();
      const auto native = std::string(rmw_get_serialization_format());
      auto output_format = settings["serialization_format"].get<std::string>();
      if (output_format.empty()) {output_format = native;}
      writer->open(storage, {native, output_format});
      writer_ = std::move(writer);
      active_session_id_ = request->session_id;
      active_bag_uri_ = uri;
      configured_topics_ = topics;
      settings_ = settings;
      context_ = context;
      subscriptions_.clear(); counts_.clear(); trigger_reasons_.clear();
      trigger_reasons_.insert(request->reason);
      error_.clear(); finish_reason_.clear(); finished_at_utc_.clear();
      started_at_utc_ = timestampUtc(); finalized_ = false;
      owner_timeout_sec_ = request->owner_timeout_sec;
      last_owner_contact_ = std::chrono::steady_clock::now();
      recording_ = true; status_ = "starting";
      response->started_new_bag = true;
      discoverTopics();
      writeMetadata(); publishState();
      response->success = true;
      response->started_new_bag = true;
      response->message = "Opened writer; inspect state for subscription readiness";
      RCLCPP_INFO(get_logger(), "Started bag %s", active_bag_uri_.c_str());
    }
  } catch (const std::exception & error) {
    response->success = false;
    response->message = error.what();
    // An error opening the new session must not stop a different owner's bag.
    if (recording_ && request->session_id == active_session_id_ && response->started_new_bag) {
      error_ = error.what(); finishRecording("start_error", true);
    }
  }
  response->recording = recording_;
  response->bag_uri = active_bag_uri_.string();
}

void BagRecorderNode::stopRecording(
  const std::shared_ptr<StopRecording::Request> request,
  std::shared_ptr<StopRecording::Response> response) {
  std::lock_guard<std::recursive_mutex> lock(mutex_);
  if (request->session_id.empty() || request->session_id != active_session_id_) {
    response->message = "Session does not own this recorder";
  } else {
    if (recording_) {finishRecording("stopped");}
    response->success = finalized_ && error_.empty();
    response->message = response->success ? "Stopped and finalized bag" : error_;
  }
  response->recording = recording_;
  response->finalized = finalized_;
  response->bag_uri = active_bag_uri_.string();
}

void BagRecorderNode::discoverTopics() {
  if (!recording_ || !writer_) {return;}
  const auto topics_and_types = get_topic_names_and_types();
  for (const auto & topic : configured_topics_) {
    if (subscriptions_.count(topic)) {continue;}
    const auto found = topics_and_types.find(topic);
    if (found == topics_and_types.end()) {continue;}
    if (found->second.size() != 1) {throw std::runtime_error("Conflicting types for " + topic);}
    if (!get_publishers_info_by_topic(topic).empty()) {subscribeTopic(topic, found->second.front());}
  }
  if (subscriptions_.size() == configured_topics_.size() && status_ != "recording") {
    status_ = "recording";
    writeMetadata(); publishState();
  }
}

void BagRecorderNode::subscribeTopic(const std::string & topic, const std::string & type) {
  const auto endpoints = get_publishers_info_by_topic(topic);
  const auto qos = rosbag2_transport::Rosbag2QoS::adapt_request_to_offers(topic, endpoints);
  YAML::Node offers(YAML::NodeType::Sequence);
  for (const auto & endpoint : endpoints) {
    offers.push_back(rosbag2_transport::Rosbag2QoS(endpoint.qos_profile()));
  }
  writer_->create_topic({topic, type, rmw_get_serialization_format(), YAML::Dump(offers)});
  counts_[topic] = 0;
  subscriptions_[topic] = create_generic_subscription(topic, type, qos,
    [this, topic, type](std::shared_ptr<rclcpp::SerializedMessage> message) {
      // Humble generic subscriptions do not expose MessageInfo. Use host callback
      // receive time for the bag index; original sensor header bytes stay intact.
      const auto received = host_clock_.now();
      std::lock_guard<std::recursive_mutex> lock(mutex_);
      if (!recording_ || !writer_) {return;}
      try {
        writer_->write(std::move(message), topic, type, received);
        ++counts_[topic];
      } catch (const std::exception & error) {
        error_ = error.what(); finishRecording("write_error", true);
      }
    });
  RCLCPP_INFO(get_logger(), "Recording topic %s [%s]", topic.c_str(), type.c_str());
}

void BagRecorderNode::finishRecording(const std::string & reason, bool failed) {
  if (!recording_) {return;}
  status_ = "stopping"; publishState();
  subscriptions_.clear();
  try {
    writer_->close(); writer_.reset();
    finalized_ = std::filesystem::is_regular_file(active_bag_uri_ / "metadata.yaml");
    if (!finalized_) {throw std::runtime_error("Bag metadata/finalization missing");}
  } catch (const std::exception & error) {
    error_ = error.what(); finalized_ = false; failed = true;
    writer_.reset();
  }
  recording_ = false; finish_reason_ = reason;
  finished_at_utc_ = timestampUtc();
  status_ = failed ? "failed" : "stopped";
  try {writeMetadata();}
  catch (const std::exception & error) {error_ = error.what(); status_ = "failed"; finalized_ = false;}
  if (rclcpp::ok(get_node_base_interface()->get_context())) {publishState();}
  RCLCPP_INFO(get_logger(), "Recorder %s: %s", status_.c_str(), active_bag_uri_.c_str());
}

Json BagRecorderNode::state() const {
  std::vector<std::string> subscribed;
  for (const auto & item : counts_) {subscribed.push_back(item.first);}
  return {{"session_id", active_session_id_}, {"status", status_}, {"recording", recording_},
    {"finalized", finalized_}, {"bag_uri", active_bag_uri_.string()}, {"error", error_},
    {"topics", configured_topics_}, {"subscribed_topics", subscribed}, {"topic_counts", counts_},
    {"settings", settings_}, {"trigger_reasons", trigger_reasons_},
    {"started_at", started_at_utc_}, {"stopped_at", finished_at_utc_}, {"finish_reason", finish_reason_},
    {"backend", "rosbag2_cpp"}, {"recorder_pid", getpid()}};
}

void BagRecorderNode::publishState() {
  if (!rclcpp::ok(get_node_base_interface()->get_context())) {return;}
  std_msgs::msg::String message; message.data = state().dump(); state_publisher_->publish(message);
}

void BagRecorderNode::writeMetadata() const {
  if (active_bag_uri_.empty()) {return;}
  auto metadata = state();
  metadata["schema_version"] = 1; metadata["context"] = context_;
  metadata["configured_output_directory"] = output_directory_.string();
  metadata["bag_index_timestamp_source"] = "host system clock at serialized subscription callback";
  metadata["rmw_implementation"] = rmw_get_implementation_identifier();
  const auto destination = active_bag_uri_ / "recording_metadata.json";
  auto temporary = destination; temporary += ".tmp";
  std::ofstream output(temporary);
  output << std::setw(2) << metadata << '\n'; output.close();
  if (!output) {throw std::runtime_error("Could not write recorder metadata");}
  std::filesystem::rename(temporary, destination);
}

std::filesystem::path BagRecorderNode::expandUserPath(const std::string & path) {
  if (path == "~" || path.rfind("~/", 0) == 0) {
    const char * user_home = std::getenv("HOME");
    if (user_home) {return path == "~" ? std::filesystem::path(user_home) : std::filesystem::path(user_home) / path.substr(2);}
  }
  return std::filesystem::path(path);
}

std::string BagRecorderNode::timestampUtc() {
  const auto time = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
  std::tm utc{}; gmtime_r(&time, &utc);
  std::ostringstream stream; stream << std::put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
  return stream.str();
}
}  // namespace musohu_bag_recorder
