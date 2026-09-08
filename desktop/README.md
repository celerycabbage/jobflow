# JobFlow Desktop（Windows x64）

这是 JobFlow 的原生 Windows 客户端。桌面端覆盖注册/登录、首次运行引导、本地服务检测与启停、投递与面试管理、批量状态/撤销/重复合并、标签与自定义字段、本地 JD 匹配、CSV/JSON/ICS、数据分析、提醒、离线队列、备份、深色模式、全局快捷键、托盘和开机启动。

## 安装或解压后直接运行

1. 把 ZIP **完整解压**到普通文件夹（不要直接在压缩包预览里运行）。
2. 双击 `JobFlow.Desktop.exe`。
3. 保留默认本机 API 地址，然后登录或创建账户。

此发布包内置桌面客户端、本地 API、SQLite 数据库和提醒调度器，不需要另外安装 .NET、Python、Docker、MySQL 或 Redis。Windows 首次运行从互联网下载的未签名 EXE 时可能显示 SmartScreen；应只使用你信任来源提供的包。

## 首次运行与本地数据

桌面端启动时会自动运行包内 `server\JobFlow.Server.exe`，API 只监听 `127.0.0.1:8000`。首次运行会在当前 Windows 用户目录创建数据库和随机签名密钥；无需联网下载运行组件。也可以跳过本地服务，填写已有的 HTTPS API 地址。

API 地址、主题和首次运行状态保存到 `%LOCALAPPDATA%\JobFlow\settings.json`。API 暂时不可用时，新建投递会进入 `%LOCALAPPDATA%\JobFlow\offline-queue.json`，下次登录后可同步。SQLite 数据库、随机密钥、日志和上传文件位于 `%LOCALAPPDATA%\JobFlow\server`；设置页可一键备份。停止服务、升级安装和普通卸载不会删除数据。

任何界面下按 `Ctrl+Shift+N` 可唤起新增投递。设置页的更新检查需要正式发布者配置可信的 `update.json` 清单地址；未配置时只显示当前版本。

## 可选：注册浏览器 Deep Link

右键 `register-protocol.ps1`，选择“使用 PowerShell 运行”，即可注册 `jobflow://`。注册后支持：

```text
jobflow://capture?company=Example&title=Backend%20Engineer&url=https%3A%2F%2Fexample.com
```

不注册协议不影响桌面端本身使用。

## 开发构建

```powershell
cd desktop\JobFlow.Desktop
dotnet restore --configfile ..\NuGet.Config
dotnet run
```

生成可分发 ZIP；构建环境需安装后端开发依赖（含 PyInstaller），若系统已安装 Inno Setup，同时生成安装器：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -c constraints.lock -e ".[dev]"
cd ..
.\tools\package-release.ps1
```
