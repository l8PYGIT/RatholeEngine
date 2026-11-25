"""rathole-tuner package constants and schema identifiers (stdlib only)."""

TUNER_VERSION = "2.4.0"
SCHEMA_VERSION = "rathole.netprofile.v1"
PROFILE_PREFIX = "rthprof1:"

MAX_FRAME_BYTES = 1048576
MAX_PROFILE_B64_LEN = 65536
MAX_PROFILE_JSON_BYTES = 524288

DEFAULT_CTRL_PORT = 29890
DEFAULT_DATA_PORT = 29891

ALLOWED_ACTIONS = frozenset({
    "hello",
    "caps",
    "snapshot",
    "heartbeat",
    "apply_cand",
    "revert",
    "stats",
    "carrier_start",
    "carrier_stop",
    "audit",
    "shutdown",
})
