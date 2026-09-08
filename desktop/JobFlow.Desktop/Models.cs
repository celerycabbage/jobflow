using System.Text.Json.Serialization;

namespace JobFlow.Desktop;

public sealed record TokenResponse([property: JsonPropertyName("access_token")] string AccessToken);

public sealed record Company(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("website")] string? Website);

public sealed record Job(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("company_id")] int CompanyId,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("location")] string? Location,
    [property: JsonPropertyName("source")] string? Source,
    [property: JsonPropertyName("source_url")] string? SourceUrl,
    [property: JsonPropertyName("jd_text")] string? JdText,
    [property: JsonPropertyName("company")] Company Company);

public sealed record ResumeVersion(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("file_name")] string? FileName,
    [property: JsonPropertyName("has_file")] bool HasFile,
    [property: JsonPropertyName("content_text")] string? ContentText,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt)
{
    public string FileLabel => HasFile ? FileName ?? "已上传文件" : "仅版本记录";
}

public sealed record ApplicationItem(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("job_id")] int JobId,
    [property: JsonPropertyName("resume_version_id")] int? ResumeVersionId,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("notes")] string? Notes,
    [property: JsonPropertyName("applied_at")] DateTimeOffset? AppliedAt,
    [property: JsonPropertyName("next_action_at")] DateTimeOffset? NextActionAt,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("updated_at")] DateTimeOffset UpdatedAt,
    [property: JsonPropertyName("archived_at")] DateTimeOffset? ArchivedAt,
    [property: JsonPropertyName("tags")] List<string> Tags,
    [property: JsonPropertyName("custom_fields")] Dictionary<string, string> CustomFields,
    [property: JsonPropertyName("job")] Job Job,
    [property: JsonPropertyName("resume_version")] ResumeVersion? ResumeVersion)
{
    public string Summary => $"{Job.Company.Name} · {Job.Title}";
    public string Metadata => $"{Labels.Status(Status)} · {Job.Location ?? "地点未填写"} · {Job.Source ?? "来源未填写"}";
    public string NextActionLabel => NextActionAt?.ToLocalTime().ToString("yyyy-MM-dd HH:mm") ?? "未设置";
    public string ScheduleState => NextActionAt is { } due && due < DateTimeOffset.UtcNow ? "已到期" : "待跟进";
}

public sealed record InterviewRound(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("application_id")] int ApplicationId,
    [property: JsonPropertyName("round_name")] string RoundName,
    [property: JsonPropertyName("interview_type")] string InterviewType,
    [property: JsonPropertyName("scheduled_at")] DateTimeOffset ScheduledAt,
    [property: JsonPropertyName("duration_minutes")] int DurationMinutes,
    [property: JsonPropertyName("location")] string? Location,
    [property: JsonPropertyName("interviewer")] string? Interviewer,
    [property: JsonPropertyName("notes")] string? Notes,
    [property: JsonPropertyName("outcome")] string? Outcome)
{
    public string TimeLabel => ScheduledAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm");
    public string StateLabel => Outcome ?? "待进行";
}

public sealed record MatchResult(
    [property: JsonPropertyName("score")] int Score,
    [property: JsonPropertyName("matched_keywords")] List<string> MatchedKeywords,
    [property: JsonPropertyName("missing_keywords")] List<string> MissingKeywords,
    [property: JsonPropertyName("questions")] List<string> Questions,
    [property: JsonPropertyName("recommendation")] string Recommendation);

public sealed record TimelineItem(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("event_type")] string EventType,
    [property: JsonPropertyName("from_status")] string? FromStatus,
    [property: JsonPropertyName("to_status")] string? ToStatus,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt)
{
    public string Change => $"{(FromStatus is null ? "—" : Labels.Status(FromStatus))} → {(ToStatus is null ? EventType : Labels.Status(ToStatus))}";
    public string TimeLabel => CreatedAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm");
}

public sealed record NotificationItem(
    [property: JsonPropertyName("id")] int Id,
    [property: JsonPropertyName("application_id")] int? ApplicationId,
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("body")] string Body,
    [property: JsonPropertyName("scheduled_for")] DateTimeOffset ScheduledFor,
    [property: JsonPropertyName("read_at")] DateTimeOffset? ReadAt)
{
    public string State => ReadAt is null ? "未读" : "已读";
    public string TimeLabel => ScheduledFor.ToLocalTime().ToString("yyyy-MM-dd HH:mm");
}

public sealed record StageInsight(
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("current_count")] int CurrentCount,
    [property: JsonPropertyName("ever_reached")] int EverReached,
    [property: JsonPropertyName("average_days_to_reach")] double? AverageDaysToReach)
{
    public string StatusLabel => Labels.Status(Status);
    public string AverageDaysLabel => AverageDaysToReach?.ToString("0.0") ?? "—";
}

public sealed record SourceInsight(
    [property: JsonPropertyName("source")] string Source,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("interviews")] int Interviews,
    [property: JsonPropertyName("offers")] int Offers);

public sealed record ResumeInsight(
    [property: JsonPropertyName("resume")] string Resume,
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("interviews")] int Interviews,
    [property: JsonPropertyName("offers")] int Offers);

public sealed record WeeklyTrend(
    [property: JsonPropertyName("week")] string Week,
    [property: JsonPropertyName("applications")] int Applications);

public sealed record DashboardInsights(
    [property: JsonPropertyName("total_applications")] int TotalApplications,
    [property: JsonPropertyName("active_applications")] int ActiveApplications,
    [property: JsonPropertyName("offer_rate")] double OfferRate,
    [property: JsonPropertyName("average_days_to_offer")] double? AverageDaysToOffer,
    [property: JsonPropertyName("stages")] List<StageInsight> Stages,
    [property: JsonPropertyName("sources")] List<SourceInsight> Sources,
    [property: JsonPropertyName("resumes")] List<ResumeInsight> Resumes,
    [property: JsonPropertyName("weekly_trend")] List<WeeklyTrend> WeeklyTrend);

public sealed record CsvImportError(
    [property: JsonPropertyName("row")] int Row,
    [property: JsonPropertyName("detail")] string Detail);

public sealed record CsvImportResult(
    [property: JsonPropertyName("imported")] int Imported,
    [property: JsonPropertyName("skipped")] int Skipped,
    [property: JsonPropertyName("errors")] List<CsvImportError> Errors);

public sealed record OfflineDraft(
    Guid Id, string Company, string Title, string? Location, string? Source, string? SourceUrl,
    string? JdText, string? Notes, int? ResumeVersionId, string Status,
    DateTimeOffset? NextActionAt, DateTimeOffset CreatedAt);

public sealed record DeepLinkData(string Company, string Title, string SourceUrl, string Notes);

public static class Labels
{
    public static string Status(string status) => status switch
    {
        "saved" => "待投递", "applied" => "已投递", "assessment" => "笔试",
        "interview" => "面试", "offer" => "Offer", "closed" => "已结束", _ => status,
    };
}
