using System.IO;
using System.Text.Json;

namespace JobFlow.Desktop;

public sealed class OfflineQueue
{
    private readonly string _path;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly JsonSerializerOptions _json = new(JsonSerializerDefaults.Web) { WriteIndented = true };

    public OfflineQueue(string? path = null)
    {
        _path = path ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "JobFlow",
            "offline-queue.json");
    }

    public async Task<IReadOnlyList<OfflineDraft>> ReadAsync()
    {
        await _gate.WaitAsync();
        try
        {
            if (!File.Exists(_path)) return [];
            await using var stream = File.OpenRead(_path);
            return await JsonSerializer.DeserializeAsync<List<OfflineDraft>>(stream, _json) ?? [];
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task AddAsync(OfflineDraft draft)
    {
        var drafts = (await ReadAsync()).ToList();
        drafts.Add(draft);
        await WriteAsync(drafts);
    }

    public async Task RemoveAsync(Guid id)
    {
        var drafts = (await ReadAsync()).Where(item => item.Id != id).ToList();
        await WriteAsync(drafts);
    }

    private async Task WriteAsync(List<OfflineDraft> drafts)
    {
        await _gate.WaitAsync();
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
            await using var stream = File.Create(_path);
            await JsonSerializer.SerializeAsync(stream, drafts, _json);
        }
        finally
        {
            _gate.Release();
        }
    }
}
