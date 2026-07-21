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
| Tektronix（泰克） | [DPO2012B](docs/tektronix/DPO2012B.md) | USBTMC/VISA | 已通过真实设备验证 |
| GW Instek（固纬） | [AFG-2125](docs/gw_instek/AFG-2125.md) | Mini USB-B / USB CDC / VISA ASRL | 控制、调制、扫频和任意波已通过真实设备闭环验证 |
| Agilent/Keysight | [33500B 系列](docs/agilent/33500B-Series.md) | USBTMC、LAN VXI-11/Socket、GPIB | 33509B USB 已测试；LAN/GPIB 已完成实现并预留验收路径 |

DPO2012B 使用机身后部的 USB Type-B 设备端口。该接口采用 USBTMC/VISA
协议，并不是串口 COM 设备，因此不能使用普通串口 MCP 控制。

AFG-2125 使用后部 Mini USB-B 端口，但实际通信方式是 USB CDC 虚拟串口，
Windows 中显示为 `AFG CDC Device (COMx)`，通过 `ASRLx::INSTR` 访问，
并不是 USBTMC。详见 [AFG-2125 使用说明](docs/gw_instek/AFG-2125.md)。

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
|   |-- tektronix/
|       |-- diagnostics.py       # Windows USB/VISA 环境诊断
|       `-- dpo2012b.py          # DPO2012B 识别、测量和波形读取
|   `-- gw_instek/
|       |-- diagnostics.py       # Windows CDC/COM/VISA ASRL 环境诊断
|       `-- afg_2125.py          # AFG-2125 波形、调制、扫频、ARB 和输出保护
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
- 其他设备：安装其接口所需的 VISA、虚拟串口或厂商驱动，并避免厂商软件、串口
  工具或其他 VISA 程序独占设备会话。

使用 DPO2012B 时，需要安装 VISA/USBTMC 驱动。本项目提供独立的
[DPO2012B 使用说明](docs/tektronix/DPO2012B.md)，其中包含已验证的
NI-VISA 15.0 Runtime 下载链接、安装日期记录和故障排查方法。安装驱动后，
请重新插拔 USB 数据线或重启示波器。正常识别后的 VISA 地址类似：

```text
USB0::0x0699::0x039D::<设备序列号>::INSTR
```

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
- `dpo2012b_acquire_waveform`：获取最多 10,000 个经过缩放的波形点
- `dpo2012b_query_scpi`：发送只读 DPO2012B SCPI 查询
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

AFG-2125 的 `APPLy` 指令会自动开启输出，因此其标准工具不使用该指令；
`afg2125_set_output(enabled=true)` 还必须传入 `confirm_enable=true`。原始高风险
命令需要 `AFG2125_ALLOW_UNSAFE=1` 和 `confirm_unsafe=true` 双重确认。

## Agilent/Keysight 33500B 系列工具

系列驱动将 USBTMC、LAN VXI-11、LAN SCPI Socket 5025 和 GPIB 建模为独立
VISA 接口。连接时识别精确型号并读取选件后再决定能力。当前实测 33509B 为
单通道 20 MHz 且没有 ARB 选件，因此会拒绝任意波命令。

工具覆盖诊断、身份/能力、标准波形、负载、脉冲和波形细节、SYNC、AM/FM/PM/
PWM/FSK/BPSK/SUM、Sweep、Burst、受保护触发，以及手册其余远程功能所需的
通用 SCPI 接口。输出开启必须传入 `confirm_enable=true`；`APPLy`、原始输出切换、
复位、自检、校准、许可证、破坏性文件操作和安全擦除默认禁止。详见
[33500B 系列说明](docs/agilent/33500B-Series.md)。

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

项目使用 MIT License。
