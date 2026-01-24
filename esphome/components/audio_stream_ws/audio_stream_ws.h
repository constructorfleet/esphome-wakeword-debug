#pragma once

#include "esphome/core/component.h"
#include "esphome/core/automation.h"
#include "esphome/core/log.h"

#ifdef USE_ESP32
#include <driver/i2s.h>
#include <WiFi.h>
#include <WebSocketsClient.h>

namespace esphome {
namespace audio_stream_ws {

static const char *const TAG = "audio_stream_ws";

class AudioStreamWS : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  void set_url(const std::string &url) { this->url_ = url; }
  void set_i2s_din_pin(int pin) { this->i2s_din_pin_ = pin; }
  void set_i2s_ws_pin(int pin) { this->i2s_ws_pin_ = pin; }
  void set_i2s_clk_pin(int pin) { this->i2s_clk_pin_ = pin; }
  void set_sample_rate(int rate) { this->sample_rate_ = rate; }
  void set_bits_per_sample(int bits) { this->bits_per_sample_ = bits; }

  void start_streaming();
  void stop_streaming();
  bool is_streaming() const { return this->streaming_; }

 protected:
  void setup_i2s_();
  void read_audio_();
  void parse_url_();
  void connect_websocket_();

  std::string url_;
  std::string ws_host_;
  uint16_t ws_port_{80};
  std::string ws_path_{"/ws/audio"};
  
  int i2s_din_pin_{-1};
  int i2s_ws_pin_{-1};
  int i2s_clk_pin_{-1};
  int sample_rate_{16000};
  int bits_per_sample_{16};
  
  bool streaming_{false};
  bool i2s_initialized_{false};
  bool ws_connected_{false};
  
  WebSocketsClient ws_client_;
  
  static const size_t BUFFER_SIZE = 512;
  uint8_t audio_buffer_[BUFFER_SIZE];
  
  static const i2s_port_t I2S_PORT = I2S_NUM_0;
};

template<typename... Ts> class StartStreamAction : public Action<Ts...>, public Parented<AudioStreamWS> {
 public:
  void play(Ts... x) override { this->parent_->start_streaming(); }
};

template<typename... Ts> class StopStreamAction : public Action<Ts...>, public Parented<AudioStreamWS> {
 public:
  void play(Ts... x) override { this->parent_->stop_streaming(); }
};

}  // namespace audio_stream_ws
}  // namespace esphome

#endif  // USE_ESP32
