using System.IO;
using System.Text.Json;

namespace JobFlow.Desktop;

public static class SelfTest
{
    public static async Task<int> RunAsync(string resultPath, string email, string password)
    {
        var checks = new Dictionary<string, object>();
        try
        {
            var apiUrl = Environment.GetEnvironmentVariable("JOBFLOW_API_URL") ?? DesktopSettings.Load().ApiBaseUrl;
            apiUrl = DesktopSettings.NormalizeApiUrl(apiUrl);
            checks["api_url"] = apiUrl;
            using var api = new ApiClient(apiUrl);
            await api.LoginAsync(email, password);
            var applications = await api.GetApplicationsAsync();
            checks["api_login"] = true;
            checks["application_count"] = applications.Count;

            var queuePath = Path.Combine(Path.GetTempPath(), $"jobflow-self-test-{Guid.NewGuid():N}.json");
            var queue = new OfflineQueue(queuePath);
            var draft = new OfflineDraft(
                Guid.NewGuid(), "Self Test", "Queue Validation", null, "self-test", null,
                "Validate the desktop offline queue", "Temporary draft", null, "saved", null,
                DateTimeOffset.UtcNow);
            await queue.AddAsync(draft);
            checks["queue_roundtrip"] = (await queue.ReadAsync()).Single().Id == draft.Id;
            await queue.RemoveAsync(draft.Id);
            checks["queue_cleanup"] = (await queue.ReadAsync()).Count == 0;
            File.Delete(queuePath);

            var deepLink = MainWindow.ParseDeepLink(
                "jobflow://capture?company=Desktop%20Labs&title=Engineer&url=https%3A%2F%2Fexample.com");
            checks["deep_link"] = deepLink is { Company: "Desktop Labs", Title: "Engineer" };
            checks["passed"] = checks.Values.OfType<bool>().All(value => value);
        }
        catch (Exception exception)
        {
            checks["passed"] = false;
            checks["error"] = exception.Message;
        }
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(resultPath))!);
        await File.WriteAllTextAsync(
            resultPath,
            JsonSerializer.Serialize(checks, new JsonSerializerOptions { WriteIndented = true }));
        return checks.TryGetValue("passed", out var passed) && passed is true ? 0 : 1;
    }
}
