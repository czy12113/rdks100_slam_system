# vlm_scene

`vlm_scene` is the ROS 2 package used by RDKS100 for VLM-based scene understanding. It subscribes to detection and camera topics, calls the selected provider, and publishes structured scene descriptions for the backend and UI.

## Providers

| Provider | Key | Notes |
|---|---|---|
| `qwen_vl` | `DASHSCOPE_API_KEY` | Default provider, DashScope/Qwen-VL compatible API. |
| `openai_vision` | `OPENAI_API_KEY` | OpenAI-compatible vision API. |
| `deepseek_text` | `DEEPSEEK_API_KEY` | Text-only fallback. |
| `internvl_local` | none | Local model placeholder. |
| `mock` | none | Offline template provider for UI integration. |

## API Keys

Do not write real keys into source code. Export them in the runtime environment:

```bash
export DASHSCOPE_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
```

Optional provider settings:

```bash
export VLM_QWEN_MODEL="qwen-vl-plus"
export VLM_QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export VLM_OPENAI_MODEL="gpt-4o-mini"
export VLM_OPENAI_BASE_URL="https://api.openai.com/v1"
export VLM_DEEPSEEK_MODEL="deepseek-chat"
export VLM_DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
```

The helper file is:

```text
vlm_scene/providers/keys.py
```

It only provides defaults and reads environment variables at runtime. Keep all key constants empty in public repositories.

## Build

```bash
cd RDKS100_Chassis_Upper_Computer/ros2_ws
colcon build --packages-select vlm_scene
source install/setup.bash
```

## Run

Default provider:

```bash
ros2 launch vlm_scene vlm.launch.py
```

Offline mock provider:

```bash
ros2 launch vlm_scene vlm.launch.py provider:=mock
```

OpenAI-compatible provider:

```bash
export OPENAI_API_KEY="sk-..."
export VLM_OPENAI_BASE_URL="https://api.openai.com/v1"
export VLM_OPENAI_MODEL="gpt-4o-mini"
ros2 launch vlm_scene vlm.launch.py provider:=openai_vision
```

Tune throttling:

```bash
ros2 launch vlm_scene vlm.launch.py cooldown_sec:=5.0 heartbeat_sec:=30.0
```

## Topics and Service

```bash
ros2 node list | grep vlm
ros2 topic echo /vlm/scene_description --once
ros2 topic echo /vlm/status --once
ros2 service call /vlm/ask std_srvs/srv/Trigger {}
```

## Troubleshooting

- `401 Unauthorized`: confirm the key is exported in the same environment that starts the node.
- Repeated descriptions: lower `cooldown_sec` or check whether the input detection results are changing.
- Offline development: use `provider:=mock`.
