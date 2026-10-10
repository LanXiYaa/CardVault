# CardVault

**存储卡备份 · SHA-256 校验 · 原生 Windows 桌面工具**

**简体中文** | [English](README.en.md)

Windows 10/11 x64 · Python + PySide6

> **AI 制作声明：本软件由 AI 制作。** 项目由用户提出需求并指导迭代，代码、界面与文档由 AI 生成和协助完善。Python、Qt、PySide6、思源黑体等第三方组件由各自作者开发，其版权与许可归各自权利人所有。

CardVault 用于将 SD 卡、TF 卡、U 盘及相机存储卡中的素材备份到电脑或其他存储设备。通过多线程复制、SHA-256 完整性校验、任务恢复与结果报告，帮助用户检查每次备份是否完成。

## 功能亮点

| 功能 | 说明 |
| --- | --- |
| 设备与目标检查 | 识别存储设备，检查目标可写性及剩余空间 |
| 多线程复制 | 每个任务 1–8 个线程，默认 3 个；最多同时运行 3 个任务 |
| 双目标备份 | 同一批素材可复制到两个目标目录并分别校验 |
| 两种校验时机 | 逐份复制后校验，或全部复制后集中校验 |
| 素材整理 | 文件类型筛选、日期分类、自定义命名、重复文件处理 |
| 错误恢复 | 失败重试、暂停和恢复任务、历史记录 |
| 实时状态 | 总进度、当前文件、复制速度与预计剩余时间 |
| 清晰报告 | 突出显示成功、失败、跳过、待处理数量，支持导出 |
| 四种界面语言 | 简体中文、繁体中文、英语、日语；首次启动按时区选择，可在设置中更改 |
| 外观设置 | 内置开源思源黑体，支持自选字体与主题色 |
| 本地更新 | 在更新页拖入新版 Setup 安装包，关闭程序后更新并重新启动 |

实际复制速度由源卡、读卡器、接口和目标磁盘共同决定，增加线程不一定线性提速。

## 安装与启动

### 使用发行版

维护者发布安装包后，可在本仓库的 **Releases** 页面获取：

- `CardVault-x.x.x-Setup-x64.exe`：安装版，运行 Setup 后从快捷方式启动。
- `CardVault-x.x.x-Windows-x64.zip`：便携版，完整解压后运行 `CardVault.exe`。

**发行版无需预装 Python 或依赖库。** 便携版请保留整个文件夹及其中的 DLL、字体和其他资源，不能只复制 EXE。源码仓库本身不包含安装包。

### 从源码运行

开发环境：Windows 10/11 x64、Python 3.13 x64；已使用 Python 3.13.7 验证。在源码根目录打开 PowerShell：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe start.py
```

直接使用 Python 入口启动，不需要 BAT 或手动激活虚拟环境。安装依赖需要联网；复制、校验和任务管理在本地执行。

## 基本使用

1. 插入存储卡，选择源设备和备份目标目录。
2. 按需设置文件筛选、分类、命名和第二个备份目标。
3. 在设置中选择线程数及校验时机。
4. 开始备份，查看复制与校验进度。
5. 完成后查看报告，检查失败和待处理项，再进行后续素材管理。

设置中的语言修改在重启后生效；字体和主题色保存后立即应用。

## 默认字体与许可

默认字体为 **思源黑体（Source Han Sans SC）**。程序内置 Adobe 官方 2.005 版的常规与粗体文件，启动时注册到当前应用，无需在系统中安装。

思源黑体**并非没有版权**，而是采用 **SIL Open Font License 1.1** 的开源字体，允许在遵守许可的条件下使用、嵌入和随软件分发。本项目保留原始字体、版权声明与完整许可证，不捆绑微软雅黑、Segoe UI 或 Consolas 字体文件。用户在设置中选择的其他系统字体仍适用其各自许可。

- [字体来源与 SHA-256](assets/fonts/README.md)
- [字体完整许可证](assets/fonts/LICENSE.txt)
- [Adobe 官方项目](https://github.com/adobe-fonts/source-han-sans)

此前保存的自选字体会继续生效；若需要切换，请在设置中选择 `Source Han Sans SC`。

## 本地安装包更新

在 **设置 → 更新** 中拖入版本更高的 CardVault Setup 安装包。程序检查安装包后将其暂存到 `update` 文件夹；执行更新时保存任务状态并退出，由独立辅助脚本等待主程序关闭，调用安装包更新原安装目录，再启动程序。

该功能使用本地安装包，不提供在线版本下载。请使用本项目对应的新版 Setup，不能用任意 EXE 或 ZIP 替代。

## 测试与打包

运行自动化测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

构建发行版需安装 Inno Setup，并将 `ISCC` 指向其实际编译器路径：

```powershell
.\.venv\Scripts\python.exe -m pip install -r packaging/requirements-build.txt
$env:ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
.\.venv\Scripts\python.exe packaging/build_release.py
```

输出位于 `release/`，包括目录式程序、Setup 安装包、便携 ZIP、源码 ZIP 和 SHA-256 校验文件。构建下载第三方许可证时需要联网。

详见 [构建与源码说明](docs/构建与源码说明.md) 与 [GitHub 推送及 Git 基础教程](docs/GitHub与Git教程.md)。

## 项目结构

```text
start.py                 启动入口
cardvault/               界面、复制引擎、语言、设备和更新逻辑
assets/                  SVG 资源、更新辅助脚本
  fonts/                 思源黑体、来源和许可证
tests/                  自动化测试与界面渲染工具
packaging/               构建、安装脚本与发行验证
docs/                   开发与 Git 使用说明
requirements.txt         运行依赖
README.md                中文说明
README.en.md             English documentation
```

## 数据与边界

- 默认只读取源卡，不删除源文件。校验结果用于检查副本完整性，不保证存储硬件永远可靠。
- 两个目标目录若位于同一物理磁盘，不能防止该磁盘故障导致两个副本同时丢失。
- 源码运行时记录位于 `data/`；安装版默认位于 `%LOCALAPPDATA%\CardVault`。记录、报告和编译产物已在 Git 忽略规则中排除。
- 日期分类基于文件修改时间；当前不以完整保留空目录、NTFS ACL 或备用数据流为目标。
- 复制速度与预计时间不包含所有校验开销；安全弹出受 Windows 和设备占用情况限制。

## 反馈与贡献

欢迎通过 Issues 描述问题，附上程序版本、Windows 版本、复现步骤及相关错误信息。提交日志前请移除个人路径和其他隐私数据。代码修改请附验证方式或相关测试结果。

## 项目许可与第三方组件

当前仓库尚未为 CardVault 应用代码指定开源许可证；公开源码不等于授予任意使用、修改或再分发权限。第三方组件保留各自许可，详见 [第三方说明](packaging/THIRD_PARTY_NOTICES.txt)。思源黑体的 OFL 许可仅适用于该字体，不替代应用代码的许可证。
