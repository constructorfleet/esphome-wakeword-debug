import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import i2s_audio
from esphome.const import CONF_ID, CONF_URL
from esphome import automation

DEPENDENCIES = ["i2s_audio"]
AUTO_LOAD = ["socket"]

audio_stream_ws_ns = cg.esphome_ns.namespace("audio_stream_ws")
AudioStreamWS = audio_stream_ws_ns.class_("AudioStreamWS", cg.Component)

# Actions
StartStreamAction = audio_stream_ws_ns.class_("StartStreamAction", automation.Action)
StopStreamAction = audio_stream_ws_ns.class_("StopStreamAction", automation.Action)

CONF_I2S_DIN_PIN = "i2s_din_pin"
CONF_I2S_WS_PIN = "i2s_ws_pin"
CONF_I2S_CLK_PIN = "i2s_clk_pin"
CONF_SAMPLE_RATE = "sample_rate"
CONF_BITS_PER_SAMPLE = "bits_per_sample"

CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(AudioStreamWS),
    cv.Required(CONF_URL): cv.url,
    cv.Required(CONF_I2S_DIN_PIN): cv.int_,
    cv.Required(CONF_I2S_WS_PIN): cv.int_,
    cv.Required(CONF_I2S_CLK_PIN): cv.int_,
    cv.Optional(CONF_SAMPLE_RATE, default=16000): cv.int_,
    cv.Optional(CONF_BITS_PER_SAMPLE, default=16): cv.one_of(16, 32),
}).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    
    cg.add(var.set_url(config[CONF_URL]))
    cg.add(var.set_i2s_din_pin(config[CONF_I2S_DIN_PIN]))
    cg.add(var.set_i2s_ws_pin(config[CONF_I2S_WS_PIN]))
    cg.add(var.set_i2s_clk_pin(config[CONF_I2S_CLK_PIN]))
    cg.add(var.set_sample_rate(config[CONF_SAMPLE_RATE]))
    cg.add(var.set_bits_per_sample(config[CONF_BITS_PER_SAMPLE]))


@automation.register_action(
    "audio_stream_ws.start",
    StartStreamAction,
    cv.Schema({
        cv.GenerateID(): cv.use_id(AudioStreamWS),
    })
)
async def start_stream_action(config, action_id, template_arg, args):
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var


@automation.register_action(
    "audio_stream_ws.stop",
    StopStreamAction,
    cv.Schema({
        cv.GenerateID(): cv.use_id(AudioStreamWS),
    })
)
async def stop_stream_action(config, action_id, template_arg, args):
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var
