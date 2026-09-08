using System.IO;
using System.Windows;

namespace JobFlow.Desktop;

public partial class App : System.Windows.Application
{
    private LocalServiceManager? _localServices;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        var selfTestIndex = Array.IndexOf(e.Args, "--self-test");
        if (selfTestIndex >= 0)
        {
            var resultPath = selfTestIndex + 1 < e.Args.Length
                ? e.Args[selfTestIndex + 1]
                : Path.Combine(Path.GetTempPath(), "jobflow-self-test.json");
            var email = Environment.GetEnvironmentVariable("JOBFLOW_TEST_EMAIL") ?? "";
            var password = Environment.GetEnvironmentVariable("JOBFLOW_TEST_PASSWORD") ?? "";
            var exitCode = await SelfTest.RunAsync(resultPath, email, password);
            Shutdown(exitCode);
            return;
        }
        _localServices = new LocalServiceManager();
        var settings = DesktopSettings.Load();
        if (settings.ApiBaseUrl.StartsWith("http://localhost:8000/", StringComparison.OrdinalIgnoreCase)
            || settings.ApiBaseUrl.StartsWith("http://127.0.0.1:8000/", StringComparison.OrdinalIgnoreCase))
        {
            try { await _localServices.StartAsync(); }
            catch (Exception) { /* The first-run and login screens surface actionable diagnostics. */ }
        }
        var window = new MainWindow(_localServices);
        if (e.Args.FirstOrDefault(arg => arg.StartsWith("jobflow://", StringComparison.OrdinalIgnoreCase)) is { } uri)
        {
            window.ApplyDeepLink(uri);
        }
        window.Show();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _localServices?.Dispose();
        base.OnExit(e);
    }
}
