# 实验设备 MCP

[English README](README_EN.md)

一个可扩展的实验室仪器 Model Context Protocol（MCP）服务。项目按照厂商和
设备型号隔离驱动，方便持续增加示波器、电源、万用表、信号发生器等实验设备，
同时避免不同型号的识别规则和控制命令互相混杂。

GitHub 仓库：<https://github.com/1622352030/lab-equipment-mcp>

## 已支持设备

| 厂商 | 型号 | 通信接口 | 验证状态 |
| --- | --- | --- | --- |
| Tektronix（泰克） | DPO2012B | USBTMC/VISA | 已通过真实设备验证 |

DPO2012B 使用机身后部的 USB Type-B 设备端口。该接口采用 USBTMC/VISA
协议，并不是串口 COM 设备，因此不能使用普通串口 MCP 控制。

## 项目结构

```text
src/lab_equipment_mcp/
|-- core/                         # 公共 VISA、异常和 SCPI 安全逻辑
|-- devices/
|   `-- tektronix/
|       |-- diagnostics.py       # Windows USB/VISA 环境诊断
|       `-- dpo2012b.py          # DPO2012B 识别、测量和波形读取
`-- server.py                    # MCP 工具注册入口
```

新增型号时，应在 `devices/<厂商>/` 下建立独立模块。通用通信逻辑放入
`core/`；设备 ID、SCPI 指令、参数范围和返回值解析等型号相关逻辑放在对应
设备驱动中。

## 环境要求

- Windows 10 或 Windows 11
- [Codex](https://developers.openai.com/codex/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)，并确保可以执行 `uvx`
- 与目标仪器匹配的 VISA Runtime

使用 DPO2012B 时，需要安装
[NI-VISA Runtime](https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html)
或包含 USBTMC 支持的 TekVISA/OpenChoice。安装驱动后，请重新插拔 USB
数据线或重启示波器。正常识别后的 VISA 地址类似：

```text
USB0::0x0699::0x039D::<设备序列号>::INSTR
```

## 安装到 Codex

### 推荐：PowerShell 一键安装

安装脚本会自动完成以下操作：

1. 查找 `codex` 和 `uvx` 的绝对路径。
2. 如果已经注册旧版 `lab-equipment`，先移除旧配置。
3. 直接从本 GitHub 仓库注册最新版 MCP。

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

GitHub 安装方式通过 `uvx` 启动指定分支。需要强制刷新缓存时执行：

```powershell
uv cache clean lab-equipment-mcp
```

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

- `dpo2012b_diagnose_setup`：检查 USB 枚举、VISA Runtime 和 PyVISA 环境
- `list_visa_instruments`：列出 VISA 仪器，并可选择读取设备身份
- `dpo2012b_connect`：自动发现或连接指定 DPO2012B VISA 地址
- `disconnect_instrument`：断开当前仪器连接
- `identify_instrument`：读取当前仪器的 `*IDN?` 身份信息
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

## 安全机制

校准、固件更新、复位、保存/恢复配置和文件删除等高风险命令默认被拦截。
如确有需要，必须同时设置服务端环境变量 `DPO2012B_ALLOW_UNSAFE=1`，并在
调用工具时传入 `confirm_unsafe=true`。标准安装方式不会启用危险命令。

## 增加其他设备

1. 新建 `src/lab_equipment_mcp/devices/<厂商>/<型号>.py`。
2. 将设备发现和身份验证逻辑放在对应设备驱动中。
3. VISA/USBTMC/GPIB/TCPIP 设备优先复用 `core.visa.VisaBackend`。
4. MCP 工具名增加型号前缀，例如 `model_measure_voltage`。
5. 添加模拟单元测试；具备实物时，再增加真实设备冒烟测试。
6. 更新本文档中的设备支持表和工具说明。

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
