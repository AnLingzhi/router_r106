# Home Assistant 路由器监控集成

这是一个 Home Assistant 自定义集成，用于监控特定型号路由器的状态（如电池电量、温度、网络信号等）。

## 功能

*   监控路由器电池电量百分比
*   监控路由器电池温度
*   监控路由器网络信号强度
*   显示路由器额外信息（如网络模式、运营商、漫游状态等）
*   支持通过 HTTP/HTTPS 代理进行所有网络请求
*   监控当前活动的 SIM 卡槽
*   提供服务以切换活动的 SIM 卡槽 (支持卡槽 "1" 和 "2")

## 安装

1.  **准备组件文件夹**:
    *   在您的计算机上，确保 `__init__.py`, `manifest.json`, 和 `sensor.py` 这三个文件位于同一个文件夹内。当前这些文件位于名为 `router_r106` 的项目文件夹中。我们将这个文件夹作为集成的根文件夹。

2.  **复制到 Home Assistant**:
    *   将包含上述三个文件的文件夹 (即 `router_r106` 文件夹) 复制到您的 Home Assistant 配置目录下的 `custom_components` 文件夹中。
    *   **最终的目录结构应如下所示**:
        ```
        <config_directory>/
        └── custom_components/
            └── router_r106/  <-- 这是您复制的项目文件夹
                ├── __init__.py
                ├── manifest.json
                └── sensor.py
        ```
        其中 `<config_directory>` 是您的 Home Assistant 配置文件夹路径 (例如 `/config` 或 `~/.homeassistant`)。

3.  **重启 Home Assistant**:
    *   为了让 Home Assistant 加载新的自定义组件，您需要重启 Home Assistant 服务。

## 配置

在您的 `configuration.yaml` 文件中添加以下配置：

```yaml
sensor:
  - platform: router_r106 # 这里填写您在 custom_components 中使用的文件夹名称
    username: "YOUR_ROUTER_USERNAME"
    password: "YOUR_ROUTER_PASSWORD"
    url: "http://192.168.1.1" # 可选，路由器的管理界面 URL，默认为 "http://192.168.1.1"
    proxy: "" # 可选，指定代理服务器地址。如果留空或省略此行，则不使用代理。示例: "http://your_proxy_ip:port"
```

**参数说明:**

*   `platform`: (必需) 必须是您在 `custom_components` 目录下放置此集成的文件夹名称 (在此示例中为 `router_r106`)。
*   `username`: (必需) 您路由器的登录用户名。
*   `password`: (必需) 您路由器的登录密码。
*   `url`: (可选) 您路由器的管理界面 URL。默认值为 `http://192.168.1.1`。
*   `proxy`: (可选) 指定用于所有出站 HTTP/HTTPS 请求的代理服务器。格式为 `http://<proxy_ip>:<proxy_port>` 或 `https://<proxy_ip>:<proxy_port>`。如果您的网络不需要代理，请将此参数值设置为空字符串 (`""`) 或直接省略此行。如果未配置，则默认不使用任何代理。

## 提供的传感器

配置完成后，此集成将提供以下传感器实体：

*   `sensor.router_battery_level`: 路由器电池电量 (%)
*   `sensor.router_battery_temperature`: 路由器电池温度 (°C)
*   `sensor.router_network_signal_level`: 路由器网络信号强度 (dB)
*   `sensor.router_extra_info`: 路由器额外信息 (状态为网络模式，属性包含运营商、漫游状态等)
*   `sensor.router_sim_slot`: 当前活动的 SIM 卡槽 (例如 "1" 或 "2")
*   `sensor.router_control`: 用于发送控制命令的实体（例如重启）。

## 服务

### `router_r106.set_sim_slot`

用于设置路由器活动的 SIM 卡槽。

**服务数据:**

| 参数        | 描述                                   | 示例    |
|-------------|----------------------------------------|---------|
| `slot_id`   | (必需) 要激活的 SIM 卡槽ID。必须是 "1" 或 "2"。 | `"1"`   |

**示例 YAML 调用:**
```yaml
service: router_r106.set_sim_slot
data:
  slot_id: "2"
```

## 注意事项

*   请确保您的 Home Assistant 实例可以访问您在配置中指定的路由器管理界面 URL。
*   如果路由器的 API 或登录机制与组件中硬编码的不符，此集成可能无法正常工作。
*   配置文件中显示的代理地址 `http://172.17.13.165:7890` 仅为填写格式示例，请根据您的实际网络环境进行配置或将其留空以不使用代理。