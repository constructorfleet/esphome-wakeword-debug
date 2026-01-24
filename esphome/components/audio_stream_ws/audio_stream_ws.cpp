#include "audio_stream_ws.h"

#ifdef USE_ESP32

namespace esphome {
namespace audio_stream_ws {

void AudioStreamWS::setup() {
  ESP_LOGCONFIG(TAG, "Setting up Audio Stream WebSocket...");
  this->parse_url_();
  this->setup_i2s_();
}

void AudioStreamWS::dump_config() {
  ESP_LOGCONFIG(TAG, "Audio Stream WebSocket:");
  ESP_LOGCONFIG(TAG, "  URL: %s", this->url_.c_str());
  ESP_LOGCONFIG(TAG, "  Host: %s", this->ws_host_.c_str());
  ESP_LOGCONFIG(TAG, "  Port: %d", this->ws_port_);
  ESP_LOGCONFIG(TAG, "  Path: %s", this->ws_path_.c_str());
  ESP_LOGCONFIG(TAG, "  Sample Rate: %d Hz", this->sample_rate_);
  ESP_LOGCONFIG(TAG, "  Bits Per Sample: %d", this->bits_per_sample_);
  ESP_LOGCONFIG(TAG, "  I2S DIN Pin: %d", this->i2s_din_pin_);
  ESP_LOGCONFIG(TAG, "  I2S WS Pin: %d", this->i2s_ws_pin_);
  ESP_LOGCONFIG(TAG, "  I2S CLK Pin: %d", this->i2s_clk_pin_);
}

void AudioStreamWS::parse_url_() {
  // Simple URL parsing: ws://host:port/path
  std::string url = this->url_;
  
  // Remove ws:// or wss://
  if (url.find("ws://") == 0) {
    url = url.substr(5);
  } else if (url.find("wss://") == 0) {
    url = url.substr(6);
    // Note: WebSocketsClient library handles wss differently
  }
  
  // Find port separator
  size_t port_pos = url.find(':');
  size_t path_pos = url.find('/');
  
  if (port_pos != std::string::npos && (path_pos == std::string::npos || port_pos < path_pos)) {
    // Has port
    this->ws_host_ = url.substr(0, port_pos);
    
    if (path_pos != std::string::npos) {
      this->ws_port_ = std::stoi(url.substr(port_pos + 1, path_pos - port_pos - 1));
      this->ws_path_ = url.substr(path_pos);
    } else {
      this->ws_port_ = std::stoi(url.substr(port_pos + 1));
    }
  } else if (path_pos != std::string::npos) {
    // No port, has path
    this->ws_host_ = url.substr(0, path_pos);
    this->ws_path_ = url.substr(path_pos);
  } else {
    // No port, no path
    this->ws_host_ = url;
  }
  
  ESP_LOGD(TAG, "Parsed URL - Host: %s, Port: %d, Path: %s", 
           this->ws_host_.c_str(), this->ws_port_, this->ws_path_.c_str());
}

void AudioStreamWS::setup_i2s_() {
  if (this->i2s_initialized_) {
    return;
  }
  
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = this->sample_rate_,
    .bits_per_sample = (i2s_bits_per_sample_t)this->bits_per_sample_,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 512,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };
  
  i2s_pin_config_t pin_config = {
    .bck_io_num = this->i2s_clk_pin_,
    .ws_io_num = this->i2s_ws_pin_,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = this->i2s_din_pin_
  };
  
  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, nullptr);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to install I2S driver: %d", err);
    this->mark_failed();
    return;
  }
  
  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to set I2S pins: %d", err);
    this->mark_failed();
    return;
  }
  
  this->i2s_initialized_ = true;
  ESP_LOGI(TAG, "I2S initialized successfully");
}

void AudioStreamWS::connect_websocket_() {
  if (this->ws_connected_) {
    return;
  }
  
  ESP_LOGI(TAG, "Connecting to WebSocket: %s:%d%s", 
           this->ws_host_.c_str(), this->ws_port_, this->ws_path_.c_str());
  
  this->ws_client_.begin(this->ws_host_.c_str(), this->ws_port_, this->ws_path_.c_str());
  
  // Set up WebSocket event handler
  this->ws_client_.onEvent([this](WStype_t type, uint8_t *payload, size_t length) {
    switch (type) {
      case WStype_DISCONNECTED:
        ESP_LOGW(TAG, "WebSocket disconnected");
        this->ws_connected_ = false;
        break;
      case WStype_CONNECTED:
        ESP_LOGI(TAG, "WebSocket connected");
        this->ws_connected_ = true;
        break;
      case WStype_ERROR:
        ESP_LOGE(TAG, "WebSocket error");
        this->ws_connected_ = false;
        break;
      default:
        break;
    }
  });
  
  // Initial connection attempt
  this->ws_client_.loop();
}

void AudioStreamWS::start_streaming() {
  if (this->streaming_) {
    ESP_LOGW(TAG, "Already streaming");
    return;
  }
  
  if (!this->i2s_initialized_) {
    ESP_LOGE(TAG, "I2S not initialized");
    return;
  }
  
  this->connect_websocket_();
  this->streaming_ = true;
  ESP_LOGI(TAG, "Started streaming");
}

void AudioStreamWS::stop_streaming() {
  if (!this->streaming_) {
    return;
  }
  
  this->streaming_ = false;
  this->ws_client_.disconnect();
  this->ws_connected_ = false;
  ESP_LOGI(TAG, "Stopped streaming");
}

void AudioStreamWS::read_audio_() {
  if (!this->streaming_ || !this->i2s_initialized_) {
    return;
  }
  
  size_t bytes_read = 0;
  esp_err_t err = i2s_read(I2S_PORT, this->audio_buffer_, BUFFER_SIZE, &bytes_read, portMAX_DELAY);
  
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Error reading I2S data: %d", err);
    return;
  }
  
  if (bytes_read > 0 && this->ws_connected_) {
    // Send raw PCM data via WebSocket
    this->ws_client_.sendBIN(this->audio_buffer_, bytes_read);
  }
}

void AudioStreamWS::loop() {
  if (this->streaming_) {
    // Keep WebSocket connection alive
    this->ws_client_.loop();
    
    // Try to reconnect if disconnected
    if (!this->ws_connected_) {
      static uint32_t last_reconnect_attempt = 0;
      uint32_t now = millis();
      if (now - last_reconnect_attempt > 5000) {  // Try every 5 seconds
        last_reconnect_attempt = now;
        ESP_LOGW(TAG, "Attempting to reconnect WebSocket...");
        this->connect_websocket_();
      }
    }
    
    // Read and send audio data
    if (this->ws_connected_) {
      this->read_audio_();
    }
  }
}

}  // namespace audio_stream_ws
}  // namespace esphome

#endif  // USE_ESP32
