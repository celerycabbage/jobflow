using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows.Interop;

namespace JobFlow.Desktop;

public sealed class LocalServiceManager : IDisposable
{
    private readonly string? _composeFile;
    private readonly string? _embeddedServer;
    private Process? _serverProcess;

    public LocalServiceManager()
    {
        var serverCandidates = new[] {
            Environment.GetEnvironmentVariable("JOBFLOW_SERVER_EXE"),
            Path.Combine(AppContext.BaseDirectory, "server", "JobFlow.Server.exe"),
        };
        _embeddedServer = serverCandidates.FirstOrDefault(path =>
            !string.IsNullOrWhiteSpace(path) && File.Exists(path));
        var candidates = new[] {
            Environment.GetEnvironmentVariable("JOBFLOW_COMPOSE_FILE"),
            Path.Combine(AppContext.BaseDirectory, "runtime", "docker-compose.yml"),
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "docker-compose.yml")),
        };
        _composeFile = candidates.FirstOrDefault(path => !string.IsNullOrWhiteSpace(path) && File.Exists(path));
    }

    public string ComposeFile => _composeFile ?? "未找到本地服务配置";
    public bool HasEmbeddedServer => _embeddedServer is not null;

    public async Task<string> DiagnoseAsync()
    {
        if (await IsHealthyAsync())
            return _embeddedServer is not null ? "内置本地服务已就绪，无需 Docker。" : "本地 API 已就绪。";
        if (_embeddedServer is not null) return "内置本地服务尚未启动。";
        if (_composeFile is null) return "未找到本地运行包。可填写远程 HTTPS API，或重新安装完整桌面包。";
        var docker = await RunAsync("docker", "version --format {{.Server.Version}}");
        if (docker.ExitCode != 0) return "Docker Desktop 未运行或未安装。启动 Docker Desktop 后重试。";
        return $"Docker {docker.Output.Trim()} 已就绪，本地 JobFlow 服务尚未启动。";
    }

    public async Task<string> StartAsync()
    {
        if (await IsHealthyAsync()) return "本地服务已就绪。";
        if (_embeddedServer is not null)
        {
            var start = new ProcessStartInfo(_embeddedServer)
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = Path.GetDirectoryName(_embeddedServer)!,
            };
            _serverProcess = Process.Start(start)
                ?? throw new InvalidOperationException("无法启动内置本地服务。");
            for (var attempt = 0; attempt < 60; attempt++)
            {
                if (_serverProcess.HasExited)
                    throw new InvalidOperationException($"内置本地服务启动失败，退出码 {_serverProcess.ExitCode}。请查看服务日志。");
                if (await IsHealthyAsync()) return "内置本地服务已启动，数据只保存在这台电脑。";
                await Task.Delay(500);
            }
            throw new TimeoutException("内置本地服务启动超时，请查看服务日志。");
        }
        if (_composeFile is null) throw new InvalidOperationException("缺少 runtime\\docker-compose.yml，请重新安装完整桌面包。");
        var result = await RunAsync("docker", $"compose -f \"{_composeFile}\" up -d");
        if (result.ExitCode != 0) throw new InvalidOperationException($"本地服务启动失败：{result.Output}");
        return "本地服务已启动。首次启动需要下载镜像，API 可能在 1–3 分钟后就绪。";
    }

    public async Task<string> StopAsync()
    {
        if (_embeddedServer is not null)
        {
            StopOwnedServer();
            return "内置本地服务已停止，数据库和上传文件均已保留。";
        }
        if (_composeFile is null) throw new InvalidOperationException("缺少本地服务配置。");
        var result = await RunAsync("docker", $"compose -f \"{_composeFile}\" stop");
        if (result.ExitCode != 0) throw new InvalidOperationException($"停止失败：{result.Output}");
        return "本地服务已停止；数据库卷和上传文件均已保留。";
    }

    public async Task<string> BackupAsync(string destination)
    {
        if (_embeddedServer is not null)
        {
            var result = await RunAsync(_embeddedServer, $"--backup \"{destination}\"");
            if (result.ExitCode != 0) throw new InvalidOperationException($"备份失败：{result.Output}");
            return $"备份已保存到 {destination}";
        }
        if (_composeFile is null) throw new InvalidOperationException("缺少本地服务配置。");
        Directory.CreateDirectory(destination);
        var stamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
        var sql = Path.Combine(destination, $"jobflow-{stamp}.sql");
        var dump = await RunAsync("docker", $"compose -f \"{_composeFile}\" exec -T mysql mysqldump -u root -plocal-root-password --single-transaction jobflow", sql);
        if (dump.ExitCode != 0) throw new InvalidOperationException($"数据库备份失败：{dump.Output}");
        var localZip = Path.Combine(destination, $"jobflow-desktop-{stamp}.zip");
        if (Directory.Exists(DesktopSettings.LocalDataDirectory))
            ZipFile.CreateFromDirectory(DesktopSettings.LocalDataDirectory, localZip);
        return $"备份已保存到 {destination}";
    }

    private static async Task<bool> IsHealthyAsync()
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(1) };
            using var response = await client.GetAsync("http://127.0.0.1:8000/health");
            return response.IsSuccessStatusCode;
        }
        catch (HttpRequestException) { return false; }
        catch (TaskCanceledException) { return false; }
    }

    private void StopOwnedServer()
    {
        if (_serverProcess is not { HasExited: false }) return;
        try
        {
            _serverProcess.Kill(entireProcessTree: true);
            _serverProcess.WaitForExit(5000);
        }
        catch (InvalidOperationException) { }
        finally
        {
            _serverProcess.Dispose();
            _serverProcess = null;
        }
    }

    public void Dispose() => StopOwnedServer();

    private static async Task<(int ExitCode, string Output)> RunAsync(string file, string arguments, string? stdoutFile = null)
    {
        var start = new ProcessStartInfo(file, arguments) { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true };
        using var process = Process.Start(start) ?? throw new InvalidOperationException($"无法启动 {file}");
        var outputTask = process.StandardOutput.ReadToEndAsync();
        var errorTask = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        var output = await outputTask;
        var error = await errorTask;
        if (stdoutFile is not null && process.ExitCode == 0) await File.WriteAllTextAsync(stdoutFile, output);
        return (process.ExitCode, string.IsNullOrWhiteSpace(error) ? output : error);
    }
}

public static class UpdateChecker
{
    public static async Task<string> CheckAsync(string? feedUrl)
    {
        var current = Assembly.GetExecutingAssembly().GetName().Version ?? new Version(0, 0);
        if (string.IsNullOrWhiteSpace(feedUrl)) return $"当前版本 {current.ToString(3)}。尚未配置发布源，正式发布时可在设置中填写 update.json 地址。";
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
        var payload = JsonSerializer.Deserialize<UpdateManifest>(await client.GetStringAsync(feedUrl), new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidOperationException("更新清单格式无效。");
        return Version.TryParse(payload.Version, out var latest) && latest > current
            ? $"发现新版本 {latest}：{payload.DownloadUrl}"
            : $"已是最新版本 {current.ToString(3)}。";
    }
    private sealed record UpdateManifest(string Version, string DownloadUrl);
}

public sealed class GlobalHotkey : IDisposable
{
    private const int Id = 0x4A46;
    private readonly HwndSource _source;
    public event Action? Pressed;
    public GlobalHotkey(System.Windows.Window window)
    {
        _source = HwndSource.FromHwnd(new WindowInteropHelper(window).Handle);
        _source.AddHook(WndProc);
        if (!RegisterHotKey(_source.Handle, Id, 0x0002 | 0x0004, 0x4E))
            throw new InvalidOperationException("全局快捷键 Ctrl+Shift+N 已被其他程序占用。");
    }
    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == 0x0312 && wParam.ToInt32() == Id) { handled = true; Pressed?.Invoke(); }
        return IntPtr.Zero;
    }
    public void Dispose() { UnregisterHotKey(_source.Handle, Id); _source.RemoveHook(WndProc); }
    [DllImport("user32.dll")] private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);
    [DllImport("user32.dll")] private static extern bool UnregisterHotKey(IntPtr hWnd, int id);
}
