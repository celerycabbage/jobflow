using System.IO;
using System.Text.Json;

namespace JobFlow.Desktop;

public sealed record DesktopSettings(
    string ApiBaseUrl,
    bool FirstRunCompleted = false,
    string Theme = "Light",
    string? UpdateFeedUrl = null,
    string? DataDirectory = null)
{
    private static readonly string SettingsDirectory = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "JobFlow");
    private static readonly string SettingsPath = Path.Combine(SettingsDirectory, "settings.json");

    public static DesktopSettings Load()
    {
        try
        {
            if (File.Exists(SettingsPath))
                return JsonSerializer.Deserialize<DesktopSettings>(File.ReadAllText(SettingsPath)) ?? Default;
        }
        catch (Exception) { }
        return Default;
    }

    public void Save()
    {
        Directory.CreateDirectory(SettingsDirectory);
        File.WriteAllText(SettingsPath, JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true }));
    }

    public static DesktopSettings Default => new("http://localhost:8000/api/v1/");

    public static string NormalizeApiUrl(string value)
    {
        var normalized = value.Trim().TrimEnd('/') + "/";
        if (!Uri.TryCreate(normalized, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https"))
            throw new ArgumentException("API 地址必须是有效的 HTTP 或 HTTPS 地址");
        return normalized;
    }

    public static string LocalDataDirectory => SettingsDirectory;
}
