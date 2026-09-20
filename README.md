# 实验设备 MCP

[English README](README_EN.md)

一个可扩展的实验室仪器 Model Context Protocol（MCP）服务。项目按照厂商和
设备型号隔离驱动，方便持续增加示波器、电源、万用表、信号发生器等实验设备，
同时避免不同型号的识别规则和控制命令互相混杂。

框架支持为同一设备声明多个通信接口，包括 USBTMC、RS-232、LAN VXI-11、
LAN 原始 Socket 和 GPIB。每个接口都可以配置独立的驱动要求、发现方式、
优先级、终止符和串口参数。

GitHub 仓库：<https://github.com/1622352030/lab-equipment-mcp>

## 已支持设备

| 厂商 | 型号 | 通信接口 | 验证状态 |
| --- | --- | --- | --- |
| Tektronix（泰克） | [DPO2012B](docs/tektronix/DPO2012B.md) | USBTMC/VISA、可选 LAN VXI-11、TEK-USB-488/GPIB | USBTMC 双通道测量、全部波形编码、二进制查询及 PNG/BMP/TIFF 截图已实机验证；LAN/GPIB 未实机验证 |
| GW Instek（固纬） | [AFG-2125](docs/gw_instek/AFG-2125.md) | Mini USB-B / USB CDC / VISA ASRL | 控制、调制、扫频和任意波已通过真实设备闭环验证 |
| Agilent/Keysight | [33500B 系列](docs/agilent/33500B-Series.md) | USBTMC、LAN VXI-11/Socket、GPIB | 33509B USB 已测试；LAN/GPIB 已完成实现并预留验收路径 |
| Agilent/Keysight | [DSO-X 2012A](docs/agilent/DSOX2012A.md) | USBTMC、可选 LAN VXI-11、可选 GPIB | USBTMC 身份、代表性只读命令及 SDG1062X CH1/CH2 接收闭环已实机验证；完整编程指南 SCPI/二进制入口已实现 |
| Siglent | [SDG1000X / SDG1062X](docs/siglent/SDG1000X.md) | USBTMC、LAN VXI-11/Socket、选配 GPIB | SDG1062X 的 USB 双通道波形、模式和 ARB 已完成示波器闭环验收；LAN VXI-11 与 Socket 5025 已完成身份、读写回读和二进制 ARB 往返验证 |
| Maynuo（美尔诺） | [M8811](docs/maynuo/M8811.md) | M133/兼容 USB-TTL、M131/RS-232、M132/RS-485 | CH340 USB-TTL 身份、设置、安全保护及 200 Ω 负载下 FIX/LIST 输出与内部测量已实机验证；M131/M132 未实机验证 |
| Fluke（福禄克） | [8808A](docs/fluke/8808A.md) | RS-232（DB9，经 USB 转串口适配器） | 身份与序列号脱敏、双消息应答协议、功能/量程/速率/格式/调节器/比对/触发/测量/远程本地已实机读回验证；`*RST`、`Save`/`Call`、面板锁定、外触发与打印模式未实机验收（原因见设备指南） |

DPO2012B 使用机身后部的 USB Type-B 设备端口进行 USBTMC/VISA 通信。安装可选
DPO2CONN 模块后，编程手册还支持 Ethernet/VXI-11；通过 TEK-USB-488 适配器可桥接 GPIB。
当前仅 USBTMC 在真实设备上验收，LAN/GPIB 尚未实机验证。

AFG-2125 使用后部 Mini USB-B 端口，但实际通信方式是 USB CDC 虚拟串口，
Windows 中显示为 `AFG CDC Device (COMx)`，通过 `ASRLx::INSTR` 访问，
并不是 USBTMC。详见 [AFG-2125 使用说明](docs/gw_instek/AFG-2125.md)。

M8811 后面板 DB9 是 5 V TTL 串口，不是标准 RS-232。必须使用 M133 或经确认的
USB-TTL 转换器；标准 RS-232 前需要 M131，RS-485 前需要 M132。接线前请阅读
[M8811 使用说明](docs/maynuo/M8811.md)。

8808A 只有 RS-232：后部 DB9 母座，管脚 2 为 RXD、3 为 TXD、5 为 GND，需要
USB 转 RS-232 适配器接入主机。串口参数（波特率、数据位、奇偶校验、回显）只能
通过前面板设置，命令既不能修改也不能读回，所以 `fluke8808a_connect` 默认使用
出厂值 9600/8/N/1，面板设置不同时传入实际值即可。详见
[8808A 使用说明](docs/fluke/8808A.md)。

## 项目结构

```text
src/lab_equipment_mcp/
|-- core/
|   |-- interfaces.py            # 设备多接口声明与会话配置
|   `-- transports/
|       `-- visa.py              # USBTMC/RS-232/LAN/GPIB VISA 后端
|-- devices/
|   |-- agilent/
|       |-- diagnostics.py       # 33500B Windows USB/VISA 环境诊断
|       `-- series_33500b.py     # 接口、选件、功能和安全控制
|       `-- dsox2012a.py         # DSO-X 2012A SCPI、测量和波形传输
|   |-- tektronix/
|       |-- diagnostics.py       # Windows USB/VISA 环境诊断
|       `-- dpo2012b.py          # DPO2012B 识别、测量和波形读取
|   `-- gw_instek/
|       |-- diagnostics.py       # Windows CDC/COM/VISA ASRL 环境诊断
|       `-- afg_2125.py          # AFG-2125 波形、调制、扫频、ARB 和输出保护
|   `-- maynuo/
|       |-- diagnostics.py       # CH340/CH341、COM 与 VISA ASRL 环境诊断
|       `-- m8811.py             # M8811 TTL/RS-232/RS-485 SCPI 和输出保护
|   `-- fluke/
|       |-- diagnostics.py       # FTDI/COM 与 VISA ASRL 环境诊断
|       `-- fluke_8808a.py       # 8808A 功能、量程、调节器和测量查询
`-- server.py                    # MCP 工具注册入口
```

新增型号时，应在 `devices/<厂商>/` 下建立独立模块。通用通信逻辑放入
`core/`；设备 ID、SCPI 指令、参数范围和返回值解析等型号相关逻辑放在对应
设备驱动中。

## 开发者 Skill

仓库提供 [`add-lab-equipment-device`](skills/add-lab-equipment-device/SKILL.md)
Skill，供 Codex 或其他兼容 Agent 按标准流程增加新设备或为已有设备增加新的
通信接口。Skill 覆盖：

- 读取用户已下载的设备手册和编程手册
- 确认接口类型、接线方式和设备实际枚举结果
- 检查驱动、VISA Runtime、串口和网络环境缺漏
- 判断依赖可否自动安装，或要求用户从厂商官网下载
- Fork、克隆、建立功能分支和提交 Pull Request 的开发流程
- 多接口建模、测试要求、真实设备验收和代码质量门槛
- SCPI 命令树核对、写入后回读、固件兼容记录和示波器闭环验收经验

显式调用示例：

```text
使用 $add-lab-equipment-device 为这个项目增加一台支持 RS-232 和 LAN 的电源。
```

## 环境要求

- Windows 10 或 Windows 11。
- [Codex](https://developers.openai.com/codex/) Desktop 或 CLI。
- [uv](https://docs.astral.sh/uv/getting-started/installation/)，并确保 PowerShell
  可以执行 `uvx.exe`。
- Git for Windows。GitHub 安装方式使用 `git+https://...` 源，`uvx` 需要 Git
  获取项目代码。
- 首次安装时能够访问 GitHub、Python 下载源和 Python 包源。公司代理、防火墙或
  完全离线环境需要预先配置代理或准备离线缓存。
- 当前用户对自己的 `uv` 缓存目录和 Codex 配置目录具有写入权限。
- 与目标仪器匹配的 VISA Runtime 和厂商设备驱动。

**不需要预先安装 Python。** 项目要求 Python 3.11 或更高版本；当电脑上没有
兼容 Python 时，`uvx` 默认会自动下载并管理隔离的 Python 运行时，然后安装
`mcp`、`pyvisa` 等依赖。用户无需手动配置 `pip` 或虚拟环境。如果设置了
`UV_PYTHON_DOWNLOADS=never`、电脑无法联网或下载源被拦截，则必须自行安装兼容
Python，或为 `uv` 准备可用的离线 Python/包缓存。

设备驱动要求：

- DPO2012B：支持 USBTMC 的 NI-VISA Runtime、TekVISA 或 OpenChoice 驱动。
- AFG-2125：GW Instek AFG-2000 USB CDC 驱动和 VISA Runtime；设备应显示为
  `AFG CDC Device (COMx)`，VISA 地址为 `ASRLx::INSTR`。
- 33500B 系列：Keysight IO Libraries Suite 或其他支持 USBTMC、VXI-11/Socket、
  GPIB 的 VISA Runtime；USB 使用后部 Type-B 设备端口。
- DSO-X 2012A：Keysight IO Libraries Suite 或支持 USBTMC 的 NI-VISA Runtime；可选
  LAN VXI-11/GPIB 需要对应的 DSOXLAN/DSOXGPIB 模块。
- M8811：Maynuo M133 或经确认的 USB-TTL 转换器、M131 后的标准 RS-232，或 M132
  后的 RS-485，再配合可将对应 COM 口暴露为 ASRL 的 VISA Runtime。禁止把后面板
  TTL DB9 直接连接到标准 RS-232 电平。
- 8808A：任意可用的 USB 转 RS-232 适配器（本机为 FTDI FT232R），再配合可将该
  COM 口暴露为 ASRL 的 VISA Runtime。电压类测量使用 `VΩ` 与 `LO` 端子。
- 其他设备：安装其接口所需的 VISA、虚拟串口或厂商驱动，并避免厂商软件、串口
  工具或其他 VISA 程序独占设备会话。

使用 DPO2012B 时，需要安装 VISA/USBTMC 驱动。本项目提供独立的
[DPO2012B 使用说明](docs/tektronix/DPO2012B.md)，其中包含已验证的
NI-VISA 15.0 Runtime 下载链接、安装日期记录和故障排查方法。安装驱动后，
请重新插拔 USB 数据线或重启示波器。正常识别后的 VISA 地址类似：

```text
USB0::0x0699::0x039D::<设备序列号>::INSTR
```

### 隐私与脱敏

仓库文档、测试夹具和诊断输出不得记录真实设备序列号、USB 实例 ID、IP 地址或完整未脱敏
的 `*IDN?` 响应。VISA 地址中的序列号统一使用 `<设备序列号>`，测试代码使用 `SERIAL`
或 `REDACTED` 占位符；固件版本、厂商 ID 和产品 ID 可在不关联具体设备时保留。

## 安装到 Codex

### 推荐：PowerShell 一键安装

安装脚本会自动完成以下操作：

1. 查找 `codex` 和 `uvx` 的绝对路径。
2. 如果已经注册旧版 `lab-equipment`，先移除旧配置。
3. 直接从本 GitHub 仓库注册最新版 MCP。

安装脚本只负责 MCP 注册，不会自动安装 Git、`uv`、VISA Runtime 或厂商设备
驱动。首次真正启动 MCP 时，`uvx` 才会解析项目并在需要时自动下载 Python 和
Python 依赖，因此第一次启动需要网络，耗时也会比后续启动更长。

使用 `uvx.exe` 的绝对路径，可以避免 Codex Desktop 没有继承 PowerShell
`PATH` 环境变量而导致 MCP 无法启动的问题。

如需先检查脚本内容：

```powershell
irm https://raw.githubusercontent.com/1622352030/lab-equipment-mcp/main/scripts/install-codex.ps1
```

执行安装：

```powershell
irm https://raw.githubusercontent.com/1622352030/lab-equipment-mcp/main/scripts/install-codex.ps1 | iex
```

安装完成后，需要**完全退出 Codex Desktop**，重新打开并创建一个**新任务**。
MCP 工具在任务创建时加载，已经打开的旧任务不会动态获得新安装的工具。

可以在新任务中输入以下内容测试：

```text
调用 lab-equipment 的 dpo2012b_diagnose_setup，告诉我 ready 是否为 true。
```

### 手动安装

```powershell
$uvx = (Get-Command uvx).Source
codex mcp add lab-equipment -- $uvx --from git+https://github.com/1622352030/lab-equipment-mcp.git@main start-lab-equipment-mcp
```

检查注册结果：

```powershell
codex mcp get lab-equipment
codex mcp list
```

### 从源码安装

需要修改或开发项目时，可以使用本地源码：

```powershell
git clone https://github.com/1622352030/lab-equipment-mcp.git
cd lab-equipment-mcp
uv sync --extra dev
$uv = (Get-Command uv).Source
codex mcp add lab-equipment -- $uv --directory $PWD run start-lab-equipment-mcp
```

## 安装到 DeepSeek Harness

DSH 通过官方 MCP client 插件连接本服务。装了 `dsh-mcp-panel` 的话可以直接在面板里增删改，不用手写 YAML。

### 面板操作

1. 打开 **设置 → 插件 → MCP**
2. 点 **添加**，弹出「添加 MCP 服务器」表单
3. 按下表填写
4. 点 **生成 patch 片段**，核对生成的片段
5. 点 **复制片段** 自行粘贴，或点 **写入 profile** → **确认写入**
   （写入走审批通道，落盘前自动备份 `cordis.patch.yml`）
6. **新建一个任务**，工具才会出现在模型侧

### 表单怎么填

| 表单字段 | 本地源码 | 远程仓库（无需先 clone） |
| --- | --- | --- |
| serverName（命名空间） | `lab` | `lab` |
| transport | `stdio` | `stdio` |
| command | `uv.exe` 的绝对路径 | `uvx.exe` 的绝对路径 |
| args（每行一个参数） | 见下方 | 见下方 |
| cwd（可选） | 留空 | 留空 |
| env（环境变量） | 留空 | 留空 |
| toolCallTimeoutMs（每次调用超时） | 留空 | 留空 |
| 自动重连 | 保持勾选 | 保持勾选 |

`serverName` 决定工具前缀：填 `lab` 时工具名是 `mcp__lab__sdg1062x_connect` 这种形式。

**args 栏（本地源码）**，每行一个参数：

```text
--directory
C:/path/to/lab-equipment-mcp
run
start-lab-equipment-mcp
```

**args 栏（远程仓库）**：

```text
--from
git+https://github.com/1622352030/lab-equipment-mcp.git@main
start-lab-equipment-mcp
```

### 验证

在会话里运行：

```text
/mcp
/mcp lab tools
/mcp lab health
```

第一条列出所有 server 的连接状态、工具数和重连次数；第二条列出本服务的全部 `mcp__lab__*` 工具；第三条在连不上时给出派生的排障建议。设置面板里还有「工具试用台」，可以选 server、选工具、填 JSON 参数直接试调，结果只显示在面板里、不进模型上下文。

### 更新后让新工具生效

已打开的任务会缓存工具列表，新增的工具不会自动出现。先刷新依赖缓存，再新建任务：

```powershell
$uvx = (Get-Command uvx).Source
& $uvx --refresh --from git+https://github.com/1622352030/lab-equipment-mcp.git@main start-lab-equipment-mcp --help
```

### 不用面板时

面板写入的就是 profile 的 patch 层文件 `<DSH_HOME>/profiles/<profile>/cordis.patch.yml`，手工追加同样内容即可：

```yaml
- insert:
    - id: mcp-lab
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: lab
        transport: stdio
        command: 'C:/Users/<you>/.local/bin/uv.exe'
        args:
          - '--directory'
          - 'C:/path/to/lab-equipment-mcp'
          - 'run'
          - 'start-lab-equipment-mcp'
```

删除用面板更省事：面板的「删除（停用）」是追加 `- id:` + `disabled: true` 覆盖，行会留在文件里，随时可以重新启用。

## 更新

GitHub 安装方式通过 `uvx` 启动指定分支。优先使用 `uvx --refresh` 强制获取
远端 `main` 并重建运行环境：

```powershell
$uvx = (Get-Command uvx).Source
& $uvx --refresh --from git+https://github.com/1622352030/lab-equipment-mcp.git@main start-lab-equipment-mcp --help
```

也可以按包名清理缓存：

```powershell
uv cache clean lab-equipment-mcp
```

如果 Windows 上存在正在运行的 MCP/`uvx` 进程，`uv cache clean` 可能因缓存锁
长时间等待。此时先断开仪器并完全退出 Codex Desktop，再重试；或直接使用上面的
`uvx --refresh`。可通过输出中的 Git 提交号确认实际构建版本。

然后完全重启 Codex Desktop，并创建一个新任务。

## 卸载

```powershell
codex mcp remove lab-equipment
```

如果已经克隆源码，也可以执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-codex.ps1
```

## DPO2012B 工具

- `list_supported_devices`：列出项目支持的设备及每台设备声明的通信接口
- `dpo2012b_diagnose_setup`：检查 USB 枚举、VISA Runtime 和 PyVISA 环境
- `list_visa_instruments`：列出 VISA 仪器，并可选择读取设备身份
- `dpo2012b_connect`：自动发现或连接指定 DPO2012B VISA 地址
- `disconnect_instrument`：断开全部仪器连接
- `identify_instrument`：仅连接一台仪器时读取其 `*IDN?`；同时连接时使用型号前缀工具
- `dpo2012b_identify`、`dpo2012b_disconnect`：单独识别或断开 DPO2012B
- `dpo2012b_get_status`：读取采集、触发和时基状态
- `dpo2012b_get_channel_settings`：读取 CH1 或 CH2 垂直设置
- `dpo2012b_measure`：测量频率、RMS、周期、幅值等参数
- `dpo2012b_acquire_waveform`：按 ASCII 或 IEEE 488.2 二进制编码获取最多 10,000 个经过缩放的波形点
- `dpo2012b_query_scpi`：发送只读 DPO2012B SCPI 查询
- `dpo2012b_command`：完整 DPO2012B 编程手册文本 SCPI 入口，覆盖未做专用工具的适用命令
- `dpo2012b_query_binary`：读取手册定义的二进制查询并以 Base64 返回
- `dpo2012b_capture_screenshot`：通过 `HARDCopy START` 获取 PNG/BMP/TIFF 屏幕截图并以 Base64 返回
- `dpo2012b_write_scpi`：发送带安全保护的设置命令

示例提示词：

```text
连接 DPO2012B，测量 CH1 的频率和 RMS，并获取 1000 个波形点。
```

## AFG-2125 工具

AFG-2125 支持基础波形、AM、FM、FSK、Sweep 和任意波形。所有标准配置工具都
要求 MAIN 先关闭；参数写入后会尽可能通过 SCPI 查询确认，最后再使用
`afg2125_set_output(confirm_enable=true)` 显式开启输出。

- `afg2125_diagnose_setup`：检查 GW Instek CDC 驱动、COM 口和 VISA ASRL
- `afg2125_connect`：通过 PnP 匹配自动发现或连接指定 AFG-2125
- `afg2125_identify`、`afg2125_disconnect`：单独识别或断开 AFG-2125
- `afg2125_get_settings`：读取函数、频率、幅度、偏置和幅度单位
- `afg2125_get_mode_settings`：读取 AM、FM、FSK 和 Sweep 启用状态
- `afg2125_set_function`、`afg2125_set_frequency`、
  `afg2125_set_amplitude`、`afg2125_set_offset`：保持输出状态不变地配置参数
- `afg2125_set_square_duty`、`afg2125_set_ramp_symmetry`：设置占空比或对称性
- `afg2125_configure_am`、`afg2125_configure_fm`、`afg2125_configure_fsk`：
  配置并回读调制参数；对应 `set_*_enabled` 工具用于关闭或单独启用模式
- `afg2125_configure_sweep`、`afg2125_set_sweep_enabled`：配置线性/对数扫频、
  起止频率、扫频时间和触发源
- `afg2125_upload_arbitrary_waveform`：下载 2–4096 个 `-511..511` 整数点
- `afg2125_select_arbitrary_waveform`：选择已下载的任意波形
- `afg2125_configure_arbitrary_waveform`：上传并选择任意波，设置频率并检查
  `频率 × 点数 <= 20 MHz` 波形速率限制
- `afg2125_set_output`：关闭输出，或经过显式确认后开启输出
- `afg2125_query_scpi`、`afg2125_write_scpi`：受保护的通用 SCPI 接口

DPO2012B 与 AFG-2125 使用独立 VISA 会话，可以在同一个 MCP 进程中同时连接。
`disconnect_instrument` 会断开全部仪器；需要只断开一台时使用对应的
`dpo2012b_disconnect` 或 `afg2125_disconnect`。

AM、FM、FSK、Sweep 和 ARB 已在 AFG-2125 固件 V1.11 上使用内部源完成真实
设备闭环验收。外部 MOD/TRIG 输入尚未接线测试，详见设备说明。

V1.11 已知兼容差异：`SOURce1:SWEep:TIME?` 查询会超时，但时间设置可生效并已
通过示波器闭环验证；Sweep 内部/立即触发源可能回读为 `INT` 而非手册示例的
`IMM`。SYNC 远程开关在该固件上未验证成功，因此不提供会误报成功的专用工具。

示例提示词：

```text
诊断并连接 AFG-2125，读取当前设置，不要开启输出。
```

```text
保持 MAIN 关闭，把 AFG-2125 配置为 10 kHz 载波、20 Hz 内部正弦调制、
50% 深度的 AM；回读参数后再询问我是否开启输出。
```

```text
把 AFG-2125 配置为 1 kHz 到 5 kHz、0.5 秒、线性立即扫频，使用 DPO2012B
CH1 的 SYNC 信号验证实际频率范围，测试后恢复原来的输出状态。
```

```text
向 AFG-2125 上传 8 点任意波，频率设为 1 kHz；检查波形速率限制，先不要开启 MAIN。
```

## 安全机制

校准、固件更新、复位、保存/恢复配置和文件删除等高风险命令默认被拦截。
如确有需要，必须同时设置服务端环境变量 `DPO2012B_ALLOW_UNSAFE=1`，并在
调用工具时传入 `confirm_unsafe=true`。标准安装方式不会启用危险命令。
DPO2012B 编程手册中的适用文本 SCPI 命令均可通过 `dpo2012b_command` 访问；
二进制波形、截图和其他二进制响应通过专用 Base64 工具返回。2026-07-26 的 USBTMC
实机复验通过 47/47 项，覆盖 SDG1062X 双通道闭环、全部 MCP 即时测量类型、ASCII 和
五种二进制波形编码的 1/2 字节读取、通用二进制查询及 PNG/BMP/TIFF 截图。固件 v1.52
的截图为裸图像字节，驱动同时兼容裸图像和 IEEE 488.2 块响应。

AFG-2125 的 `APPLy` 指令会自动开启输出，因此其标准工具不使用该指令；
`afg2125_set_output(enabled=true)` 还必须传入 `confirm_enable=true`。原始高风险
命令需要 `AFG2125_ALLOW_UNSAFE=1` 和 `confirm_unsafe=true` 双重确认。

33500B 系列和 SDG1062X 的输出开启同样必须传入 `confirm_enable=true`。两者的
复位、校准、固件、许可证、破坏性文件操作和原始输出切换默认禁止；确需使用受保护的
高风险通用 SCPI 时，必须分别设置 `AGILENT33500B_ALLOW_UNSAFE=1` 或
`SDG1062X_ALLOW_UNSAFE=1`，并同时传入 `confirm_unsafe=true`。

## Agilent/Keysight 33500B 系列工具

系列驱动将 USBTMC、LAN VXI-11、LAN SCPI Socket 5025 和 GPIB 建模为独立
VISA 接口。连接时识别精确型号并读取选件后再决定能力。当前实测 33509B 为
单通道 20 MHz 且没有 ARB 选件，因此会拒绝任意波命令。

工具覆盖诊断、身份/能力、标准波形、负载、脉冲和波形细节、SYNC、AM/FM/PM/
PWM/FSK/BPSK/SUM、Sweep、Burst、受保护触发，以及手册其余远程功能所需的
通用 SCPI 接口。

- `agilent33500b_diagnose_setup`：检查 Windows USB 枚举、VISA Runtime、PyVISA
  和可识别的 33500B 系列资源
- `agilent33500b_connect`：自动发现或连接指定 USBTMC、LAN VXI-11/Socket 或 GPIB
  VISA 地址，并读取精确型号、固件和选件
- `agilent33500b_identify`、`agilent33500b_disconnect`：单独识别或断开 33500B
  系列设备
- `agilent33500b_get_capabilities`：读取型号、固件、选件、通道数、带宽、ARB能力和
  支持接口
- `agilent33500b_get_settings`：读取输出、基础波形、SYNC、调制、Sweep 和 Burst 状态
- `agilent33500b_set_waveform`：在输出关闭时设置正弦、方波、三角波、斜波、脉冲、
  PRBS、噪声或 DC 的频率、幅度和偏置
- `agilent33500b_set_output_load`：设置 1 Ω 到 10 kΩ 的预期负载，或设为高阻
- `agilent33500b_set_waveform_detail`：设置方波占空比、斜波对称性、相位或输出极性
- `agilent33500b_configure_pulse`：设置脉冲周期、宽度/占空比及上升和下降时间
- `agilent33500b_configure_sync`：配置前面板 TTL Sync 输出、模式和极性
- `agilent33500b_set_mode_enabled`：单独启用或关闭调制、Sweep 或 Burst 模式
- `agilent33500b_configure_modulation`：配置 AM、FM、PM、PWM、FSK、BPSK 或 SUM，
  并按型号和选件检查能力
- `agilent33500b_configure_sweep`：配置线性/对数扫频、触发源和可选 Sync 标记频率
- `agilent33500b_configure_burst`：配置触发或门控 Burst、周期数、相位和触发源
- `agilent33500b_trigger`：经过 `confirm_trigger=true` 确认后向已准备的 Sweep/Burst
  发送总线触发
- `agilent33500b_set_output`：自由关闭输出；开启时必须传入 `confirm_enable=true`
- `agilent33500b_query_scpi`、`agilent33500b_write_scpi`：受保护的通用 SCPI 查询和
  设置接口

当前实测 33509B 没有 ARB 选件，因此能力查询会报告 ARB 不可用，驱动也会拒绝相关
功能，而不是假定手册中的系列选件已经安装。详细接口、型号差异和实机验收记录见
[33500B 系列说明](docs/agilent/33500B-Series.md)。

示例提示词：

```text
诊断并连接 33500B 系列信号发生器，读取精确型号、固件、已安装选件和当前设置，
保持输出关闭。
```

```text
保持 33500B 输出关闭，配置 10 kHz、1 Vpp、0 V 偏置的正弦波，设置高阻负载并回读；
完成后再询问我是否开启输出。
```

```text
把 33500B 配置为 1 kHz 到 5 kHz、1 秒的线性扫频，使用内部立即触发；不要开启输出。
```

## Siglent SDG1000X / SDG1062X 工具

SDG1000X 系列驱动支持 SDG1032X 和双通道 SDG1062X。USB Type-B 实际通信方式为
USBTMC/VISA，不是串口；LAN VXI-11、LAN SCPI Socket 5025 和选配 GPIB 也作为独立
接口建模。SDG1062X 已通过 DPO2012B 双通道物理闭环验收，并使用 Agilent/Keysight
DSO-X 2012A 作为第二台双通道接收示波器完成闭环：CH1 设为 1 kHz/0.5 Vpp，实测
1000.0 Hz/0.52 Vpp；CH2 设为 2 kHz/0.5 Vpp，实测 2000.0 Hz/0.52 Vpp；接收波形
样本 Vpp 分别为 0.518 V 和 0.515 V。

LAN 已在固件 1.01.01.30R1 上完成实测：VXI-11 和 Socket 5025 两条通道都能读取身份、
写入并回读波形参数、切换 50 Ω 负载，并完成 4 点用户任意波的上传与读回比对，读回的
16 位样本与上传值逐点一致。VISA 不会像枚举 USB 那样列出 LAN 仪器，因此必须把地址
显式传入；连接时可以直接给 IP（走 VXI-11）或 `IP:5025`（走 Socket）。同步、外部
调制/触发和 GPIB 仍未实测。

- `sdg1062x_diagnose_setup`：检查 Siglent USB 枚举、VISA Runtime、PyVISA 和可识别
  的 SDG1000X 资源；传入 `lan_hosts` 时对指定 LAN 地址做只读 `*IDN?` 探测
- `sdg1062x_connect`：自动发现或连接指定 USBTMC、LAN 或 GPIB VISA 地址，并验证
  SDG1032X/SDG1062X 身份；LAN 可直接传 `10.0.0.230`（VXI-11）或 `10.0.0.230:5025`
  （Socket），也可传完整 VISA 资源
- `sdg1062x_identify`、`sdg1062x_disconnect`：单独识别或断开 Siglent SDG，身份返回
  中的序列号已脱敏
- `sdg1062x_get_capabilities`：读取通道数、最大频率、采样率、垂直分辨率、ARB点数和
  支持接口
- `sdg1062x_get_settings`：按通道读取输出、基础波形、调制、Sweep、Burst、ARB 和
  Sync 状态
- `sdg1062x_set_waveform`：在指定通道输出关闭时设置基础波形、频率、幅度和偏置
- `sdg1062x_set_waveform_detail`：设置占空比、对称性、相位、脉宽、边沿或延迟
- `sdg1062x_set_output_load`、`sdg1062x_set_output_polarity`：设置通道预期负载和
  正常/反相极性
- `sdg1062x_set_mode_enabled`：按通道启用或关闭调制、Sweep 或 Burst
- `sdg1062x_configure_modulation`：配置 AM、DSB-AM、FM、PM、PWM、ASK、FSK 或 PSK
- `sdg1062x_configure_sweep`：配置线性、对数或步进扫频、方向和触发源
- `sdg1062x_configure_burst`：配置 N周期、无限周期或门控 Burst
- `sdg1062x_trigger`：经过 `confirm_trigger=true` 确认后触发指定通道的 Sweep/Burst
- `sdg1062x_configure_sync`：配置后面板 Aux In/Out CMOS Sync 输出及源通道
- `sdg1062x_copy_channel`：在两路输出均关闭时复制通道参数并回读验证
- `sdg1062x_select_arbitrary_waveform`：选择内建 ARB 编号或用户任意波名称
- `sdg1062x_upload_arbitrary_waveform`：上传 2–16,384 个 `-1..1` 归一化点，使用
  16位小端二进制传输，并设置频率、幅度、偏置和相位
- `sdg1062x_read_arbitrary_waveform`：读回已存用户任意波并解析 16 位小端样本，用于
  校验二进制传输，可用 `max_samples` 限制返回样本数
- `sdg1062x_set_output`：按通道自由关闭输出；开启时必须传入 `confirm_enable=true`
- `sdg1062x_query_scpi`、`sdg1062x_write_scpi`：受保护的通用 SCPI 查询和设置接口

SDG1062X 的两个通道共享同一个 VISA 仪器连接，但每个通道的输出、基础波形和高级模式
独立配置。与 DPO2012B、AFG-2125 和 33500B 的 VISA 会话相互独立。详细接口、固件
差异和闭环测试结果见 [SDG1000X / SDG1062X 说明](docs/siglent/SDG1000X.md)。

示例提示词：

```text
诊断并连接 SDG1062X，读取两个通道的设置和设备能力，保持 CH1、CH2 输出关闭。
```

```text
保持两路输出关闭，将 SDG1062X CH1 配置为 1 kHz、1 Vpp 正弦波，CH2 配置为
2.5 kHz、0.8 Vpp、30% 占空比方波；回读后再询问我是否同时开启两路输出。
```

```text
向 SDG1062X CH1 上传一个 8 点归一化任意波，设为 1 kHz、0.5 Vpp、0 V 偏置，
验证选择和参数回读，但不要开启输出。
```

```text
将 SDG1062X CH1 配置为 1 kHz 到 5 kHz、1 秒线性扫频，并使用 DPO2012B CH1
进行物理闭环验收；测试后关闭输出并恢复原设置。
```

## Agilent/Keysight DSO-X 2012A 工具

DSO-X 2012A 使用后部 USB DEVICE Type-B 端口进行 USBTMC/VISA 通信，并声明可选
LAN VXI-11 和 GPIB 接口。编程指南中的完整 SCPI 命令树通过
`agilentdsox2012a_command` 提供；波形、显示、设置等 IEEE 488.2 二进制块通过
Base64 工具传输。

- `agilentdsox2012a_connect`、`agilentdsox2012a_identify`、`agilentdsox2012a_disconnect`
- `agilentdsox2012a_get_capabilities`、`agilentdsox2012a_get_status`
- `agilentdsox2012a_get_channel_settings`、`agilentdsox2012a_measure`
- `agilentdsox2012a_acquire_waveform`
- `agilentdsox2012a_query_scpi`、`agilentdsox2012a_write_scpi`、完整 `agilentdsox2012a_command`
- `agilentdsox2012a_query_binary`、`agilentdsox2012a_write_binary`

DSO-X 2012A 已完成 USB 身份、通道查询、采集设置、测量源、波形前导码和 SDG1062X
双通道接收闭环实测。闭环结果为 CH1 1 kHz/0.5 Vpp -> 1000.0 Hz/0.52 Vpp，CH2
2 kHz/0.5 Vpp -> 2000.0 Hz/0.52 Vpp。LAN、GPIB、MSO 数字通道和未安装选件仍未实测。
所有输出测试均在结束时关闭信号源并恢复示波器状态。

## Maynuo M8811 工具

M8811 驱动明确区分后面板 5 V TTL DB9 与标准 RS-232。驱动会枚举已连接的
CH340/CH341，并将其当前 COM 编号匹配到 VISA ASRL 资源；只有唯一候选时才自动选择，
存在多个候选时要求显式指定。M131/RS-232 和 M132/RS-485 链路也已分别建模。
`m8811_connect` 可按仪器面板设置选择 4800/9600/19200/38400 波特率和
none/even/odd 校验；这些参数只配置电脑端串口，不会远程修改仪器面板配置。
LIST 的 200 步存储会随 1/2/4/8 个区域联动为每区 200/100/50/25 步，相关工具会按
当前区域配置检查步号、步数和召回区域。

- `m8811_diagnose_setup`、`m8811_connect`、`m8811_identify`、`m8811_disconnect`
- `m8811_get_settings`、`m8811_measure`
- `m8811_set_voltage`、`m8811_set_current`、`m8811_set_voltage_protection`
- `m8811_set_output`、`m8811_set_mode`
- `m8811_configure_list`、`m8811_set_list_step`、`m8811_recall_list`
- `m8811_set_remote_sense`、`m8811_set_panel_control`、`m8811_clear_amp_hours`
- `m8811_query_scpi`、`m8811_write_scpi`

CH340 USB-TTL 身份、设置读回、保护门、FIX 输出和 LIST 两级循环已在固件 V2.6 上
实机验证。200 Ω 负载下，1 V FIX 实测 0.9985 V/4.87 mA，LIST 的 1 V/2 V 稳定值约为
0.999 V/4.9 mA 和 1.999 V/9.9 mA。5 V 和 10 V 又分别持续输出 20 秒，实测稳定在
约 5.000 V/24.86 mA 和 10.001 V/49.86 mA。`MEAS:AHRD?` 与 `MEAS:DRM?` 在该固件上超时；
DVM、DRM、远端采样和非默认串口参数因未接对应接口或未改面板设置而未实测。
文档不记录动态分配的 COM 编号和设备序列号。接线、完整 SCPI 覆盖和安全策略见
[M8811 使用说明](docs/maynuo/M8811.md)。

## Fluke 8808A 工具

8808A 是 5-1/2 位双显示万用表，通过 RS-232 控制，命令集是 Fluke 私有助记符
（`VDC`、`OHMS`、`FREQ` 等）而非纯 SCPI。串口参数只能通过前面板设置，命令既
不能修改也不能读回，因此 `fluke8808a_connect` 默认使用出厂值 9600/8/N/1，并在
面板设置不同时接受覆盖参数（波特率、数据位、停止位、奇偶校验、流控、回显）。
`fluke8808a_diagnose_setup` 会列出所有 COM 口并标出 FTDI 适配器，只有唯一候选
时才自动选择。

- `fluke8808a_diagnose_setup`、`fluke8808a_connect`、`fluke8808a_identify`、`fluke8808a_disconnect`
- `fluke8808a_clear_status`、`fluke8808a_get_status`、`fluke8808a_get_event_status`
- `fluke8808a_set_event_status_enable`、`fluke8808a_set_service_request_enable`
- `fluke8808a_operation_complete`、`fluke8808a_operation_complete_query`、`fluke8808a_wait`
- `fluke8808a_reset`、`fluke8808a_trigger`、`fluke8808a_self_test`、`fluke8808a_interrupt`
- `fluke8808a_set_function`、`fluke8808a_get_function`、`fluke8808a_set_wire_mode`、`fluke8808a_clear_secondary`
- `fluke8808a_set_decibel`、`fluke8808a_set_decibel_reference`、`fluke8808a_get_decibel_reference`、`fluke8808a_set_decibel_power`
- `fluke8808a_set_hold`、`fluke8808a_set_hold_threshold`
- `fluke8808a_set_max`、`fluke8808a_set_min`、`fluke8808a_set_min_max`、`fluke8808a_clear_min_max`
- `fluke8808a_set_relative`、`fluke8808a_clear_relative`、`fluke8808a_get_relative`、`fluke8808a_get_modifier`
- `fluke8808a_set_auto_range`、`fluke8808a_get_auto_range`、`fluke8808a_set_range`、`fluke8808a_get_range`
- `fluke8808a_set_rate`、`fluke8808a_get_rate`
- `fluke8808a_measure_primary`、`fluke8808a_measure_secondary`、`fluke8808a_measure`
- `fluke8808a_read_value_primary`、`fluke8808a_read_value_secondary`、`fluke8808a_read_value`
- `fluke8808a_set_compare`、`fluke8808a_get_compare`、`fluke8808a_set_compare_limits`
- `fluke8808a_set_trigger_type`、`fluke8808a_get_trigger_type`
- `fluke8808a_set_output_format`、`fluke8808a_get_output_format`、`fluke8808a_set_print_rate`
- `fluke8808a_get_serial`、`fluke8808a_set_remote_local`
- `fluke8808a_save_configuration`、`fluke8808a_recall_configuration`
- `fluke8808a_query_scpi`、`fluke8808a_write_scpi`

工具覆盖手册第 4 章表 4-8～4-18 的全部命令组，并有覆盖测试确保每条手册命令都
能实际发出、且不会发出手册之外的命令。

在固件 `1.1r D2.0` 上实机验证：身份与序列号脱敏、协议时序、10 个测量功能、
量程 1-7、速率 S/M/F、调节器全组（保持、相对、最小/最大、分贝）、比对三种判定
（PASS/LO/HI）、触发类型、输出格式、`Save`/`Call` 精确还原、`*RST` 回到出厂
状态、远程/本地、打印模式、回显开启、双显示。以 SDG1062X 作为信号源的接收
闭环：直流 ±1/2 V 误差约 1 mV，正弦与方波交流电压、100 Hz～10 kHz 频率（误差
为 0）、交流加直流有效值。外部触发类型 2-5（需 DB9 第 9 脚接 TTL 信号）、
`*TST?`（该固件未实现）与总线 SRQ（摘要位不置位）未实测。

实测发现多处手册与固件差异：错误提示为 `?>`/`!>` 而非 `?`/`!`、错误回复之后没有
确认、`^C` 回两条确认、`MAXSET`/`MINSET`/`MNMXSET` 只存值而不进入模式、
`*RST` 需 2.8 秒才应答且不重置输出格式。`*IDN?` 与 `SERIAL?` 两处的序列号均已
脱敏。协议细节、双显示开启方法和完整功能对照表见
[8808A 使用说明](docs/fluke/8808A.md)。

## 增加其他设备

1. 新建 `src/lab_equipment_mcp/devices/<厂商>/<型号>.py`。
2. 使用 `DeviceProfile` 和多个 `InterfaceSpec` 声明该型号支持的全部接口。
3. 将设备发现和身份验证逻辑放在对应设备驱动中。
4. VISA/USBTMC/GPIB/TCPIP/ASRL 设备优先复用
   `core.transports.visa.VisaBackend`。
5. MCP 工具名增加型号前缀，例如 `model_measure_voltage`。
6. 添加模拟单元测试；具备实物时，再增加真实设备冒烟测试。
7. 更新本文档中的设备支持表、接口测试状态和工具说明。

## 开发与测试

```powershell
git clone https://github.com/1622352030/lab-equipment-mcp.git
cd lab-equipment-mcp
uv sync --extra dev
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run python scripts/verify_mcp.py
uv run python scripts/verify_mcp.py --github
```

## 社区与项目使用

- 提交代码前请阅读 [贡献指南](CONTRIBUTING.md) 和 [行为准则](CODE_OF_CONDUCT.md)。
- 安全漏洞和可能导致仪器危险状态的问题请按 [安全策略](SECURITY.md) 私下报告。
- 安装、驱动和设备兼容问题请先阅读 [支持说明](SUPPORT.md)，再选择对应的 Issue 模板。
- 课程、论文、评奖和竞赛使用必须遵循 [竞赛与学术使用声明](COMPETITION_USE.md)：显著披露
  本项目及具体提交，区分既有工作和新增工作，不得冒充原创，也不得暗示维护者官方参赛或背书。

项目使用 MIT License。
