using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.IO;
using System.Text.Json;

namespace JobFlow.Desktop;

public sealed class ApiClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly JsonSerializerOptions _json = new(JsonSerializerDefaults.Web);

    public ApiClient(string baseUrl)
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl), Timeout = TimeSpan.FromSeconds(15) };
    }

    public bool IsAuthenticated => _http.DefaultRequestHeaders.Authorization is not null;
    public string BaseUrl => _http.BaseAddress!.ToString();

    public Task LoginAsync(string email, string password, CancellationToken cancellationToken = default) =>
        AuthenticateAsync("auth/login", email, password, cancellationToken);

    public Task RegisterAsync(string email, string password, CancellationToken cancellationToken = default) =>
        AuthenticateAsync("auth/register", email, password, cancellationToken);

    private async Task AuthenticateAsync(string path, string email, string password, CancellationToken cancellationToken)
    {
        using var response = await _http.PostAsJsonAsync(path, new { email, password }, _json, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        var token = await response.Content.ReadFromJsonAsync<TokenResponse>(_json, cancellationToken)
            ?? throw new InvalidOperationException("登录响应缺少令牌");
        _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token.AccessToken);
    }

    public async Task ChangePasswordAsync(string currentPassword, string newPassword, CancellationToken cancellationToken = default) =>
        await PatchAsync<object?>("auth/password", new { current_password = currentPassword, new_password = newPassword }, cancellationToken);

    public Task DeleteAccountAsync(CancellationToken cancellationToken = default) => DeleteAsync("auth/account", cancellationToken);

    public Task<List<ApplicationItem>> GetApplicationsAsync(bool archived = false, string? query = null, string? status = null, CancellationToken cancellationToken = default)
    {
        var parameters = new List<string> { $"archived={archived.ToString().ToLowerInvariant()}", "limit=200" };
        if (!string.IsNullOrWhiteSpace(query)) parameters.Add($"q={Uri.EscapeDataString(query.Trim())}");
        if (!string.IsNullOrWhiteSpace(status)) parameters.Add($"status={Uri.EscapeDataString(status)}");
        return GetAsync<List<ApplicationItem>>($"applications?{string.Join('&', parameters)}", cancellationToken);
    }

    public Task<List<Company>> GetCompaniesAsync(CancellationToken cancellationToken = default) => GetAsync<List<Company>>("companies", cancellationToken);
    public Task<List<ResumeVersion>> GetResumesAsync(CancellationToken cancellationToken = default) => GetAsync<List<ResumeVersion>>("resumes", cancellationToken);
    public Task<DashboardInsights> GetInsightsAsync(CancellationToken cancellationToken = default) => GetAsync<DashboardInsights>("dashboard/insights", cancellationToken);
    public Task<List<NotificationItem>> GetNotificationsAsync(bool unreadOnly = false, CancellationToken cancellationToken = default) => GetAsync<List<NotificationItem>>($"notifications?unread_only={unreadOnly.ToString().ToLowerInvariant()}", cancellationToken);
    public Task<List<TimelineItem>> GetTimelineAsync(int applicationId, CancellationToken cancellationToken = default) => GetAsync<List<TimelineItem>>($"applications/{applicationId}/timeline", cancellationToken);

    public Task<Company> CreateCompanyAsync(string name, string? website, CancellationToken cancellationToken = default) =>
        PostAsync<Company>("companies", new { name, website = EmptyToNull(website) }, cancellationToken);
    public Task<Company> UpdateCompanyAsync(int id, string name, string? website, CancellationToken cancellationToken = default) =>
        PatchAsync<Company>($"companies/{id}", new { name, website = EmptyToNull(website) }, cancellationToken);
    public Task DeleteCompanyAsync(int id, CancellationToken cancellationToken = default) => DeleteAsync($"companies/{id}", cancellationToken);

    public Task<ResumeVersion> CreateResumeAsync(string name, CancellationToken cancellationToken = default) =>
        PostAsync<ResumeVersion>("resumes", new { name }, cancellationToken);
    public Task<ResumeVersion> RenameResumeAsync(int id, string name, CancellationToken cancellationToken = default) =>
        PatchAsync<ResumeVersion>($"resumes/{id}", new { name }, cancellationToken);
    public Task<ResumeVersion> UpdateResumeTextAsync(int id, string name, string? contentText, CancellationToken cancellationToken = default) =>
        PatchAsync<ResumeVersion>($"resumes/{id}", new { name, content_text = EmptyToNull(contentText) }, cancellationToken);
    public Task DeleteResumeAsync(int id, CancellationToken cancellationToken = default) => DeleteAsync($"resumes/{id}", cancellationToken);

    public async Task<ResumeVersion> UploadResumeAsync(string name, string filePath, CancellationToken cancellationToken = default)
    {
        using var form = new MultipartFormDataContent();
        form.Add(new StringContent(name), "name");
        await using var stream = File.OpenRead(filePath);
        using var file = new StreamContent(stream);
        file.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(file, "file", Path.GetFileName(filePath));
        using var response = await _http.PostAsync("resumes/upload", form, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await ReadAsync<ResumeVersion>(response, cancellationToken);
    }

    public Task DownloadResumeAsync(int id, string destination, CancellationToken cancellationToken = default) =>
        DownloadAsync($"resumes/{id}/download", destination, cancellationToken);

    public Task UpdateStatusAsync(int applicationId, string status, CancellationToken cancellationToken = default) =>
        PatchAsync<ApplicationItem>($"applications/{applicationId}/status", new { status }, cancellationToken);
    public Task UpdateApplicationAsync(int id, int? resumeId, string? notes, DateTimeOffset? nextActionAt, IEnumerable<string>? tags = null, Dictionary<string, string>? customFields = null, CancellationToken cancellationToken = default) =>
        PatchAsync<ApplicationItem>($"applications/{id}", new { resume_version_id = resumeId, notes = EmptyToNull(notes), next_action_at = nextActionAt, tags, custom_fields = customFields }, cancellationToken);
    public Task UpdateJobAsync(Job job, int companyId, string title, string? location, string? source, string? sourceUrl, string? jdText, CancellationToken cancellationToken = default) =>
        PatchAsync<Job>($"jobs/{job.Id}", new { company_id = companyId, title, location = EmptyToNull(location), source = EmptyToNull(source), source_url = EmptyToNull(sourceUrl), jd_text = EmptyToNull(jdText) }, cancellationToken);
    public Task DeleteApplicationAsync(int id, CancellationToken cancellationToken = default) => DeleteAsync($"applications/{id}", cancellationToken);
    public Task ArchiveApplicationAsync(int id, CancellationToken cancellationToken = default) => PatchAsync<ApplicationItem>($"applications/{id}/archive", null, cancellationToken);
    public Task RestoreApplicationAsync(int id, CancellationToken cancellationToken = default) => PatchAsync<ApplicationItem>($"applications/{id}/restore", null, cancellationToken);
    public Task<ApplicationItem> UndoStatusAsync(int id, CancellationToken cancellationToken = default) =>
        PostAsync<ApplicationItem>($"applications/{id}/undo-status", new { }, cancellationToken);
    public Task<List<ApplicationItem>> BulkStatusAsync(IEnumerable<int> ids, string status, CancellationToken cancellationToken = default) =>
        PatchAsync<List<ApplicationItem>>("application-actions/bulk-status", new { application_ids = ids, status }, cancellationToken);
    public Task<ApplicationItem> MergeAsync(int targetId, int sourceId, CancellationToken cancellationToken = default) =>
        PostAsync<ApplicationItem>($"applications/{targetId}/merge", new { source_application_id = sourceId }, cancellationToken);
    public Task<MatchResult> GetMatchAsync(int id, CancellationToken cancellationToken = default) =>
        GetAsync<MatchResult>($"applications/{id}/match", cancellationToken);
    public Task<List<InterviewRound>> GetInterviewsAsync(int id, CancellationToken cancellationToken = default) =>
        GetAsync<List<InterviewRound>>($"applications/{id}/interviews", cancellationToken);
    public Task<InterviewRound> CreateInterviewAsync(int applicationId, string name, DateTimeOffset scheduledAt, CancellationToken cancellationToken = default) =>
        PostAsync<InterviewRound>($"applications/{applicationId}/interviews", new { round_name = name, interview_type = "video", scheduled_at = scheduledAt, duration_minutes = 60 }, cancellationToken);
    public Task DeleteInterviewAsync(int id, CancellationToken cancellationToken = default) => DeleteAsync($"interviews/{id}", cancellationToken);

    public async Task CreateApplicationAsync(OfflineDraft draft, CancellationToken cancellationToken = default)
    {
        var companies = await GetCompaniesAsync(cancellationToken);
        var company = companies.FirstOrDefault(item => string.Equals(item.Name.Trim(), draft.Company.Trim(), StringComparison.OrdinalIgnoreCase))
            ?? await CreateCompanyAsync(draft.Company.Trim(), null, cancellationToken);
        var source = string.IsNullOrWhiteSpace(draft.Source)
            ? (Uri.TryCreate(draft.SourceUrl, UriKind.Absolute, out var uri) ? uri.Host.Replace("www.", "", StringComparison.OrdinalIgnoreCase) : "desktop")
            : draft.Source.Trim();
        var job = await PostAsync<Job>("jobs", new
        {
            company_id = company.Id,
            title = draft.Title.Trim(),
            location = EmptyToNull(draft.Location),
            source,
            source_url = EmptyToNull(draft.SourceUrl),
            jd_text = EmptyToNull(draft.JdText),
        }, cancellationToken);
        await PostAsync<ApplicationItem>("applications", new
        {
            job_id = job.Id,
            resume_version_id = draft.ResumeVersionId,
            status = string.IsNullOrWhiteSpace(draft.Status) ? "saved" : draft.Status,
            notes = EmptyToNull(draft.Notes),
            next_action_at = draft.NextActionAt,
        }, cancellationToken);
    }

    public async Task<CsvImportResult> ImportCsvAsync(string filePath, CancellationToken cancellationToken = default)
    {
        using var form = new MultipartFormDataContent();
        await using var stream = File.OpenRead(filePath);
        using var file = new StreamContent(stream);
        file.Headers.ContentType = new MediaTypeHeaderValue("text/csv");
        form.Add(file, "file", Path.GetFileName(filePath));
        using var response = await _http.PostAsync("applications-import.csv", form, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await ReadAsync<CsvImportResult>(response, cancellationToken);
    }

    public Task ExportCsvAsync(string destination, CancellationToken cancellationToken = default) =>
        DownloadAsync("applications-export.csv", destination, cancellationToken);

    public Task ExportJsonAsync(string destination, CancellationToken cancellationToken = default) =>
        DownloadAsync("applications-export.json", destination, cancellationToken);

    public Task ExportCalendarAsync(string destination, CancellationToken cancellationToken = default) =>
        DownloadAsync("calendar.ics", destination, cancellationToken);

    public async Task MarkNotificationReadAsync(int id, CancellationToken cancellationToken = default) =>
        await PatchAsync<NotificationItem>($"notifications/{id}/read", null, cancellationToken);

    private async Task<T> GetAsync<T>(string path, CancellationToken cancellationToken)
    {
        using var response = await _http.GetAsync(path, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await ReadAsync<T>(response, cancellationToken);
    }

    private async Task<T> PostAsync<T>(string path, object payload, CancellationToken cancellationToken)
    {
        using var response = await _http.PostAsJsonAsync(path, payload, _json, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await ReadAsync<T>(response, cancellationToken);
    }

    private async Task<T> PatchAsync<T>(string path, object? payload, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Patch, path);
        if (payload is not null) request.Content = JsonContent.Create(payload, options: _json);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        if (response.StatusCode == HttpStatusCode.NoContent) return default!;
        return await ReadAsync<T>(response, cancellationToken);
    }

    private async Task DeleteAsync(string path, CancellationToken cancellationToken)
    {
        using var response = await _http.DeleteAsync(path, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
    }

    private async Task DownloadAsync(string path, string destination, CancellationToken cancellationToken)
    {
        using var response = await _http.GetAsync(path, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        await using var source = await response.Content.ReadAsStreamAsync(cancellationToken);
        await using var target = File.Create(destination);
        await source.CopyToAsync(target, cancellationToken);
    }

    private async Task<T> ReadAsync<T>(HttpResponseMessage response, CancellationToken cancellationToken) =>
        await response.Content.ReadFromJsonAsync<T>(_json, cancellationToken) ?? throw new InvalidOperationException("API 返回空数据");

    private static string? EmptyToNull(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static async Task EnsureSuccessAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        if (response.IsSuccessStatusCode) return;
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        string? detail = null;
        try
        {
            var value = JsonDocument.Parse(body).RootElement.GetProperty("detail");
            detail = value.ValueKind == JsonValueKind.String ? value.GetString() : value.ToString();
        }
        catch (JsonException) { }
        throw new ApiException(response.StatusCode, detail ?? $"API 请求失败：{(int)response.StatusCode}");
    }

    public void Dispose() => _http.Dispose();
}

public sealed class ApiException(HttpStatusCode statusCode, string message) : Exception(message)
{
    public HttpStatusCode StatusCode { get; } = statusCode;
}
