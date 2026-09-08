using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Net.Http;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using Microsoft.Win32;
using Forms = System.Windows.Forms;
using MessageBox = System.Windows.MessageBox;
using OpenFileDialog = Microsoft.Win32.OpenFileDialog;
using SaveFileDialog = Microsoft.Win32.SaveFileDialog;

namespace JobFlow.Desktop;

public partial class MainWindow : Window
{
    private DesktopSettings _settings;
    private ApiClient _api;
    private readonly OfflineQueue _queue = new();
    private readonly ObservableCollection<ApplicationItem> _applications = [];
    private readonly ObservableCollection<ApplicationItem> _schedule = [];
    private readonly ObservableCollection<Company> _companies = [];
    private readonly ObservableCollection<ResumeVersion> _resumes = [];
    private readonly ObservableCollection<NotificationItem> _notifications = [];
    private readonly ObservableCollection<TimelineItem> _timeline = [];
    private readonly ObservableCollection<InterviewRound> _interviews = [];
    private readonly DispatcherTimer _notificationTimer;
    private readonly Forms.NotifyIcon _trayIcon;
    private bool _explicitExit;
    private readonly LocalServiceManager _localServices;
    private GlobalHotkey? _globalHotkey;

    public MainWindow(LocalServiceManager? localServices = null)
    {
        _localServices = localServices ?? new LocalServiceManager();
        _settings = DesktopSettings.Load();
        _api = new ApiClient(_settings.ApiBaseUrl);
        InitializeComponent();
        LoginApiUrlInput.Text = _settings.ApiBaseUrl;
        SettingsApiUrlInput.Text = _settings.ApiBaseUrl;
        StartWithWindowsInput.IsChecked = StartupManager.IsEnabled;
        DarkModeInput.IsChecked = _settings.Theme == "Dark";
        ApplyTheme(_settings.Theme);
        ApplicationList.ItemsSource = _applications;
        ScheduleList.ItemsSource = _schedule;
        CompanyList.ItemsSource = _companies;
        ResumeList.ItemsSource = _resumes;
        NotificationList.ItemsSource = _notifications;
        TimelineList.ItemsSource = _timeline;
        InterviewList.ItemsSource = _interviews;
        EditCompanyInput.ItemsSource = _companies;
        EditResumeInput.ItemsSource = _resumes;
        CreateResumeInput.ItemsSource = _resumes;

        _notificationTimer = new DispatcherTimer { Interval = TimeSpan.FromMinutes(1) };
        _notificationTimer.Tick += async (_, _) => await PollNotificationsAsync();
        _trayIcon = new Forms.NotifyIcon { Text = "JobFlow Desktop", Icon = System.Drawing.SystemIcons.Application, Visible = true };
        _trayIcon.DoubleClick += (_, _) => RestoreWindow();
        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add("打开 JobFlow", null, (_, _) => RestoreWindow());
        menu.Items.Add("退出", null, (_, _) => ExitApplication());
        _trayIcon.ContextMenuStrip = menu;
        StateChanged += (_, _) => { if (WindowState == WindowState.Minimized) Hide(); };
        Closing += MainWindow_Closing;
        SourceInitialized += (_, _) => InitializeHotkey();
        Loaded += async (_, _) =>
        {
            await UpdateQueueStatusAsync();
            FirstRunApiUrl.Text = _settings.ApiBaseUrl;
            FirstRunPanel.Visibility = _settings.FirstRunCompleted ? Visibility.Collapsed : Visibility.Visible;
            LocalServiceStatus.Text = _localServices.HasEmbeddedServer
                ? $"客户端与服务端数据：{DesktopSettings.LocalDataDirectory}"
                : $"客户端数据：{DesktopSettings.LocalDataDirectory}；服务端数据：Docker 命名卷 jobflow-desktop_jobflow_*";
        };
    }

    public void ApplyDeepLink(string value)
    {
        var data = ParseDeepLink(value);
        if (data is null) return;
        CompanyInput.Text = data.Company;
        TitleInput.Text = data.Title;
        SourceUrlInput.Text = data.SourceUrl;
        NotesInput.Text = data.Notes;
        Composer.Visibility = Visibility.Visible;
    }

    public static DeepLinkData? ParseDeepLink(string value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) || !string.Equals(uri.Scheme, "jobflow", StringComparison.OrdinalIgnoreCase)) return null;
        var query = System.Web.HttpUtility.ParseQueryString(uri.Query);
        return new DeepLinkData(query["company"] ?? "", query["title"] ?? "", query["url"] ?? "", query["notes"] ?? "");
    }

    private async void LoginButton_Click(object sender, RoutedEventArgs e) => await AuthenticateAsync(register: false);
    private async void RegisterButton_Click(object sender, RoutedEventArgs e) => await AuthenticateAsync(register: true);

    private async Task AuthenticateAsync(bool register)
    {
        LoginButton.IsEnabled = RegisterButton.IsEnabled = false;
        LoginStatus.Text = register ? "正在创建账户…" : "正在登录…";
        try
        {
            ApplyLoginApiUrl();
            if (register) await _api.RegisterAsync(EmailInput.Text.Trim(), PasswordInput.Password);
            else await _api.LoginAsync(EmailInput.Text.Trim(), PasswordInput.Password);
            LoginPanel.Visibility = Visibility.Collapsed;
            Workspace.Visibility = Visibility.Visible;
            LoginStatus.Text = "";
            await RefreshAllAsync();
            await SyncQueueAsync();
            await PollNotificationsAsync();
            _notificationTimer.Start();
        }
        catch (Exception exception) { LoginStatus.Text = FriendlyError(exception); }
        finally { LoginButton.IsEnabled = RegisterButton.IsEnabled = true; }
    }

    private void ApplyLoginApiUrl()
    {
        var normalized = DesktopSettings.NormalizeApiUrl(LoginApiUrlInput.Text);
        if (string.Equals(normalized, _api.BaseUrl, StringComparison.OrdinalIgnoreCase)) return;
        _api.Dispose();
        _settings = _settings with { ApiBaseUrl = normalized };
        _settings.Save();
        _api = new ApiClient(normalized);
        SettingsApiUrlInput.Text = normalized;
    }

    private async Task RefreshAllAsync()
    {
        if (!_api.IsAuthenticated) return;
        try
        {
            await RefreshApplicationsAsync();
            var companiesTask = _api.GetCompaniesAsync();
            var resumesTask = _api.GetResumesAsync();
            var scheduleTask = _api.GetApplicationsAsync();
            var insightsTask = _api.GetInsightsAsync();
            var notificationsTask = _api.GetNotificationsAsync(UnreadOnlyInput.IsChecked == true);
            await Task.WhenAll(companiesTask, resumesTask, scheduleTask, insightsTask, notificationsTask);
            Replace(_companies, companiesTask.Result);
            Replace(_resumes, resumesTask.Result);
            Replace(_schedule, scheduleTask.Result.Where(item => item.NextActionAt is not null).OrderBy(item => item.NextActionAt));
            Replace(_notifications, notificationsTask.Result);
            ShowInsights(insightsTask.Result);
            ConnectionStatus.Text = "API 已连接";
            WorkspaceStatus.Text = "";
        }
        catch (Exception exception)
        {
            ConnectionStatus.Text = "API 离线";
            WorkspaceStatus.Text = FriendlyError(exception);
        }
        await UpdateQueueStatusAsync();
    }

    private async Task RefreshApplicationsAsync()
    {
        var status = (FilterStatusInput.SelectedItem as ComboBoxItem)?.Tag as string;
        var items = await _api.GetApplicationsAsync(ArchivedInput.IsChecked == true, SearchInput.Text, status);
        Replace(_applications, items);
        if (ApplicationList.SelectedItem is null) ClearApplicationEditor();
    }

    private static void Replace<T>(ObservableCollection<T> target, IEnumerable<T> source)
    {
        target.Clear();
        foreach (var item in source) target.Add(item);
    }

    private void ShowInsights(DashboardInsights insight)
    {
        MetricTotal.Text = insight.TotalApplications.ToString();
        MetricActive.Text = insight.ActiveApplications.ToString();
        MetricOfferRate.Text = $"{insight.OfferRate:0.##}%";
        MetricOfferDays.Text = insight.AverageDaysToOffer is { } days ? $"{days:0.0} 天" : "—";
        StageInsightList.ItemsSource = insight.Stages;
        SourceInsightList.ItemsSource = insight.Sources;
        ResumeInsightList.ItemsSource = insight.Resumes;
        WeeklyTrendList.ItemsSource = insight.WeeklyTrend;
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs e) => await RefreshAllAsync();
    private async void SearchButton_Click(object sender, RoutedEventArgs e) => await RunUiActionAsync(RefreshApplicationsAsync);
    private async void ApplicationFilter_Changed(object sender, RoutedEventArgs e)
    {
        if (IsLoaded && _api.IsAuthenticated) await RunUiActionAsync(RefreshApplicationsAsync);
    }

    private void ShowComposer_Click(object sender, RoutedEventArgs e) => Composer.Visibility = Visibility.Visible;
    private void HideComposer_Click(object sender, RoutedEventArgs e) { Composer.Visibility = Visibility.Collapsed; ComposerStatus.Text = ""; }

    private async void SaveDraftButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(CompanyInput.Text) || string.IsNullOrWhiteSpace(TitleInput.Text))
        {
            ComposerStatus.Text = "公司名称和岗位名称不能为空";
            return;
        }
        try
        {
            var draft = new OfflineDraft(Guid.NewGuid(), CompanyInput.Text.Trim(), TitleInput.Text.Trim(), EmptyToNull(LocationInput.Text),
                EmptyToNull(SourceInput.Text), EmptyToNull(SourceUrlInput.Text), EmptyToNull(JdInput.Text), EmptyToNull(NotesInput.Text),
                CreateResumeInput.SelectedValue as int?, SelectedStatus(CreateStatusInput), ParseOptionalDate(NextActionInput.Text), DateTimeOffset.UtcNow);
            try
            {
                await _api.CreateApplicationAsync(draft);
                ClearComposer();
                Composer.Visibility = Visibility.Collapsed;
                await RefreshAllAsync();
            }
            catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException)
            {
                await _queue.AddAsync(draft);
                ComposerStatus.Text = "API 当前不可用，已保存到本机离线队列";
                ClearComposer();
                await UpdateQueueStatusAsync();
            }
        }
        catch (Exception exception) { ComposerStatus.Text = FriendlyError(exception); }
    }

    private async Task SyncQueueAsync()
    {
        if (!_api.IsAuthenticated) return;
        var drafts = await _queue.ReadAsync();
        foreach (var draft in drafts)
        {
            try { await _api.CreateApplicationAsync(draft); await _queue.RemoveAsync(draft.Id); }
            catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException) { break; }
            catch (ApiException exception) { WorkspaceStatus.Text = $"离线草稿“{draft.Title}”同步失败：{exception.Message}"; break; }
        }
        await RefreshAllAsync();
    }

    private async void SyncButton_Click(object sender, RoutedEventArgs e) => await RunUiActionAsync(SyncQueueAsync);
    private async Task UpdateQueueStatusAsync() => QueueStatus.Text = $"离线队列：{(await _queue.ReadAsync()).Count}";

    private async void ApplicationList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        _timeline.Clear();
        if (ApplicationList.SelectedItem is not ApplicationItem application) { ClearApplicationEditor(); return; }
        EditTitleInput.Text = application.Job.Title;
        EditCompanyInput.SelectedValue = application.Job.CompanyId;
        EditLocationInput.Text = application.Job.Location ?? "";
        EditSourceInput.Text = application.Job.Source ?? "";
        EditSourceUrlInput.Text = application.Job.SourceUrl ?? "";
        EditJdInput.Text = application.Job.JdText ?? "";
        EditNotesInput.Text = application.Notes ?? "";
        EditTagsInput.Text = string.Join(", ", application.Tags ?? []);
        EditCustomFieldsInput.Text = string.Join(Environment.NewLine, (application.CustomFields ?? []).Select(item => $"{item.Key}: {item.Value}"));
        EditNextActionInput.Text = application.NextActionAt?.ToLocalTime().ToString("yyyy-MM-dd HH:mm") ?? "";
        EditResumeInput.SelectedValue = application.ResumeVersionId;
        EditStatusInput.SelectedItem = EditStatusInput.Items.Cast<ComboBoxItem>().FirstOrDefault(item => Equals(item.Tag, application.Status));
        ArchiveButton.Content = application.ArchivedAt is null ? "归档" : "恢复";
        try { Replace(_interviews, await _api.GetInterviewsAsync(application.Id)); }
        catch (Exception exception) { WorkspaceStatus.Text = FriendlyError(exception); }
    }

    private async void SaveApplicationButton_Click(object sender, RoutedEventArgs e)
    {
        if (ApplicationList.SelectedItem is not ApplicationItem application) { WorkspaceStatus.Text = "请先选择投递"; return; }
        await RunUiActionAsync(async () =>
        {
            var companyId = EditCompanyInput.SelectedValue is int selectedCompanyId ? selectedCompanyId : application.Job.CompanyId;
            await _api.UpdateJobAsync(application.Job, companyId, EditTitleInput.Text.Trim(), EditLocationInput.Text, EditSourceInput.Text, EditSourceUrlInput.Text, EditJdInput.Text);
            var status = SelectedStatus(EditStatusInput);
            if (!string.Equals(status, application.Status, StringComparison.Ordinal)) await _api.UpdateStatusAsync(application.Id, status);
            var tags = EditTagsInput.Text.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            var fields = EditCustomFieldsInput.Text.Split('\n', StringSplitOptions.RemoveEmptyEntries)
                .Select(line => line.Split(':', 2)).Where(parts => parts.Length == 2)
                .ToDictionary(parts => parts[0].Trim(), parts => parts[1].Trim());
            await _api.UpdateApplicationAsync(application.Id, EditResumeInput.SelectedValue as int?, EditNotesInput.Text, ParseOptionalDate(EditNextActionInput.Text), tags, fields);
            await RefreshAllAsync();
        }, "投递已更新");
    }

    private async void ArchiveButton_Click(object sender, RoutedEventArgs e)
    {
        if (ApplicationList.SelectedItem is not ApplicationItem application) { WorkspaceStatus.Text = "请先选择投递"; return; }
        await RunUiActionAsync(async () =>
        {
            if (application.ArchivedAt is null) await _api.ArchiveApplicationAsync(application.Id);
            else await _api.RestoreApplicationAsync(application.Id);
            await RefreshAllAsync();
        }, application.ArchivedAt is null ? "投递已归档" : "投递已恢复");
    }

    private async void DeleteApplicationButton_Click(object sender, RoutedEventArgs e)
    {
        if (ApplicationList.SelectedItem is not ApplicationItem application) return;
        if (MessageBox.Show($"确定删除“{application.Summary}”吗？", "删除投递", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes) return;
        await RunUiActionAsync(async () => { await _api.DeleteApplicationAsync(application.Id); await RefreshAllAsync(); }, "投递已删除");
    }

    private async void LoadTimelineButton_Click(object sender, RoutedEventArgs e)
    {
        if (ApplicationList.SelectedItem is not ApplicationItem application) return;
        await RunUiActionAsync(async () => Replace(_timeline, await _api.GetTimelineAsync(application.Id)));
    }

    private async void ImportCsvButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog { Filter = "CSV 文件 (*.csv)|*.csv" };
        if (dialog.ShowDialog() != true) return;
        await RunUiActionAsync(async () =>
        {
            var result = await _api.ImportCsvAsync(dialog.FileName);
            await RefreshAllAsync();
            MessageBox.Show($"导入 {result.Imported} 条，跳过 {result.Skipped} 条，错误 {result.Errors.Count} 条", "CSV 导入");
        });
    }

    private async void ExportCsvButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new SaveFileDialog { Filter = "CSV 文件 (*.csv)|*.csv", FileName = "jobflow-applications.csv" };
        if (dialog.ShowDialog() != true) return;
        await RunUiActionAsync(() => _api.ExportCsvAsync(dialog.FileName), "CSV 已导出");
    }

    private async void ExportJsonButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new SaveFileDialog { Filter = "JSON 文件 (*.json)|*.json", FileName = "jobflow-applications.json" };
        if (dialog.ShowDialog() == true) await RunUiActionAsync(() => _api.ExportJsonAsync(dialog.FileName), "JSON 已导出");
    }

    private async void BulkStatusButton_Click(object sender, RoutedEventArgs e)
    {
        var ids = ApplicationList.SelectedItems.Cast<ApplicationItem>().Select(item => item.Id).ToList();
        var status = (BatchStatusInput.SelectedItem as ComboBoxItem)?.Tag as string;
        if (ids.Count == 0 || string.IsNullOrWhiteSpace(status)) { WorkspaceStatus.Text = "请多选投递并选择目标状态"; return; }
        await RunUiActionAsync(async () => { await _api.BulkStatusAsync(ids, status); await RefreshAllAsync(); }, $"已更新 {ids.Count} 条投递");
    }

    private async void MergeSelectedButton_Click(object sender, RoutedEventArgs e)
    {
        var selected = ApplicationList.SelectedItems.Cast<ApplicationItem>().ToList();
        if (selected.Count != 2) { WorkspaceStatus.Text = "合并重复项需要恰好选择 2 条；第一条为保留项"; return; }
        if (MessageBox.Show($"保留“{selected[0].Summary}”并合并删除另一条记录？", "合并重复投递", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes) return;
        await RunUiActionAsync(async () => { await _api.MergeAsync(selected[0].Id, selected[1].Id); await RefreshAllAsync(); }, "重复投递已合并");
    }

    private async void UndoStatusButton_Click(object sender, RoutedEventArgs e)
    {
        if (ApplicationList.SelectedItem is not ApplicationItem application) return;
        await RunUiActionAsync(async () => { await _api.UndoStatusAsync(application.Id); await RefreshAllAsync(); }, "已撤销最近一次状态变化");
    }

    private async void MatchButton_Click(object sender, RoutedEventArgs e)
    {
        if (ApplicationList.SelectedItem is not ApplicationItem application) return;
        await RunUiActionAsync(async () =>
        {
            var result = await _api.GetMatchAsync(application.Id);
            MatchResultText.Text = $"匹配 {result.Score} 分 · {result.Recommendation}\n已匹配：{string.Join("、", result.MatchedKeywords)}\n待补充：{string.Join("、", result.MissingKeywords)}\n{string.Join(Environment.NewLine, result.Questions)}";
        });
    }

    private async void AddInterviewButton_Click(object sender, RoutedEventArgs e)
    {
        if (ApplicationList.SelectedItem is not ApplicationItem application) return;
        if (!DateTime.TryParse(RoundAtInput.Text, out var localTime)) { WorkspaceStatus.Text = "面试时间格式应为 yyyy-MM-dd HH:mm"; return; }
        await RunUiActionAsync(async () =>
        {
            await _api.CreateInterviewAsync(application.Id, RoundNameInput.Text.Trim(), new DateTimeOffset(localTime));
            Replace(_interviews, await _api.GetInterviewsAsync(application.Id));
            await RefreshAllAsync();
        }, "面试轮次已添加；如与现有面试重叠会被阻止");
    }

    private async void DeleteInterviewButton_Click(object sender, RoutedEventArgs e)
    {
        if (InterviewList.SelectedItem is not InterviewRound interview || ApplicationList.SelectedItem is not ApplicationItem application) return;
        await RunUiActionAsync(async () => { await _api.DeleteInterviewAsync(interview.Id); Replace(_interviews, await _api.GetInterviewsAsync(application.Id)); }, "面试轮次已删除");
    }

    private async void ExportCalendarButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new SaveFileDialog { Filter = "iCalendar 文件 (*.ics)|*.ics", FileName = "jobflow-calendar.ics" };
        if (dialog.ShowDialog() == true) await RunUiActionAsync(() => _api.ExportCalendarAsync(dialog.FileName), "日历已导出，可导入 Outlook、Apple Calendar 或 Google Calendar");
    }

    private async void CreateResumeButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(ResumeNameInput.Text)) { WorkspaceStatus.Text = "请输入简历版本名称"; return; }
        await RunUiActionAsync(async () => { await _api.CreateResumeAsync(ResumeNameInput.Text.Trim()); ResumeNameInput.Clear(); await RefreshAllAsync(); }, "简历版本已创建");
    }

    private async void UploadResumeButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(ResumeNameInput.Text)) { WorkspaceStatus.Text = "请输入简历版本名称"; return; }
        var dialog = new OpenFileDialog { Filter = "简历文件|*.pdf;*.doc;*.docx" };
        if (dialog.ShowDialog() != true) return;
        await RunUiActionAsync(async () => { await _api.UploadResumeAsync(ResumeNameInput.Text.Trim(), dialog.FileName); ResumeNameInput.Clear(); await RefreshAllAsync(); }, "简历已上传");
    }

    private async void RenameResumeButton_Click(object sender, RoutedEventArgs e)
    {
        if (ResumeList.SelectedItem is not ResumeVersion resume || string.IsNullOrWhiteSpace(ResumeNameInput.Text)) { WorkspaceStatus.Text = "请选择简历并输入新名称"; return; }
        await RunUiActionAsync(async () => { await _api.RenameResumeAsync(resume.Id, ResumeNameInput.Text.Trim()); ResumeNameInput.Clear(); await RefreshAllAsync(); }, "简历已重命名");
    }

    private async void SaveResumeTextButton_Click(object sender, RoutedEventArgs e)
    {
        if (ResumeList.SelectedItem is not ResumeVersion resume) { WorkspaceStatus.Text = "请先选择简历版本"; return; }
        await RunUiActionAsync(async () => { await _api.UpdateResumeTextAsync(resume.Id, resume.Name, ResumeTextInput.Text); await RefreshAllAsync(); }, "简历匹配文本已保存，仅由本地规则分析");
    }

    private void ResumeList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ResumeList.SelectedItem is ResumeVersion resume)
        {
            ResumeNameInput.Text = resume.Name;
            ResumeTextInput.Text = resume.ContentText ?? "";
        }
    }

    private async void DownloadResumeButton_Click(object sender, RoutedEventArgs e)
    {
        if (ResumeList.SelectedItem is not ResumeVersion { HasFile: true } resume) { WorkspaceStatus.Text = "请选择已上传文件的简历"; return; }
        var dialog = new SaveFileDialog { FileName = resume.FileName ?? $"{resume.Name}.pdf" };
        if (dialog.ShowDialog() == true) await RunUiActionAsync(() => _api.DownloadResumeAsync(resume.Id, dialog.FileName), "简历已下载");
    }

    private async void DeleteResumeButton_Click(object sender, RoutedEventArgs e)
    {
        if (ResumeList.SelectedItem is not ResumeVersion resume) return;
        if (MessageBox.Show($"确定删除简历版本“{resume.Name}”吗？", "删除简历", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes) return;
        await RunUiActionAsync(async () => { await _api.DeleteResumeAsync(resume.Id); await RefreshAllAsync(); }, "简历已删除");
    }

    private void CompanyList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (CompanyList.SelectedItem is not Company company) return;
        CompanyNameInput.Text = company.Name;
        CompanyWebsiteInput.Text = company.Website ?? "";
    }

    private async void CreateCompanyButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(CompanyNameInput.Text)) { WorkspaceStatus.Text = "请输入公司名称"; return; }
        await RunUiActionAsync(async () => { await _api.CreateCompanyAsync(CompanyNameInput.Text.Trim(), CompanyWebsiteInput.Text); ClearCompanyEditor(); await RefreshAllAsync(); }, "公司已创建");
    }

    private async void UpdateCompanyButton_Click(object sender, RoutedEventArgs e)
    {
        if (CompanyList.SelectedItem is not Company company || string.IsNullOrWhiteSpace(CompanyNameInput.Text)) { WorkspaceStatus.Text = "请选择公司"; return; }
        await RunUiActionAsync(async () => { await _api.UpdateCompanyAsync(company.Id, CompanyNameInput.Text.Trim(), CompanyWebsiteInput.Text); await RefreshAllAsync(); }, "公司已更新");
    }

    private async void DeleteCompanyButton_Click(object sender, RoutedEventArgs e)
    {
        if (CompanyList.SelectedItem is not Company company) return;
        if (MessageBox.Show($"确定删除公司“{company.Name}”吗？", "删除公司", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes) return;
        await RunUiActionAsync(async () => { await _api.DeleteCompanyAsync(company.Id); ClearCompanyEditor(); await RefreshAllAsync(); }, "公司已删除");
    }

    private async void RefreshNotificationsButton_Click(object sender, RoutedEventArgs e) => await RunUiActionAsync(async () => Replace(_notifications, await _api.GetNotificationsAsync(UnreadOnlyInput.IsChecked == true)));
    private async void MarkNotificationReadButton_Click(object sender, RoutedEventArgs e)
    {
        if (NotificationList.SelectedItem is not NotificationItem item) return;
        await RunUiActionAsync(async () => { await _api.MarkNotificationReadAsync(item.Id); Replace(_notifications, await _api.GetNotificationsAsync(UnreadOnlyInput.IsChecked == true)); }, "提醒已标记为已读");
    }

    private async Task PollNotificationsAsync()
    {
        if (!_api.IsAuthenticated) return;
        try
        {
            var notifications = await _api.GetNotificationsAsync(unreadOnly: true);
            foreach (var item in notifications.Take(3))
            {
                _trayIcon.ShowBalloonTip(5000, item.Title, item.Body, Forms.ToolTipIcon.Info);
                await _api.MarkNotificationReadAsync(item.Id);
            }
        }
        catch (Exception) { }
    }

    private void SaveApiSettingsButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var url = DesktopSettings.NormalizeApiUrl(SettingsApiUrlInput.Text);
            _settings = _settings with { ApiBaseUrl = url };
            _settings.Save();
            LogoutToLogin(url, "API 地址已保存，请重新登录");
        }
        catch (Exception exception) { WorkspaceStatus.Text = FriendlyError(exception); }
    }


    private async void DiagnoseServiceButton_Click(object sender, RoutedEventArgs e)
    {
        LocalServiceStatus.Text = "正在检测本地服务与 API…";
        LocalServiceStatus.Text = await _localServices.DiagnoseAsync();
    }

    private async void StartServiceButton_Click(object sender, RoutedEventArgs e) =>
        await RunServiceActionAsync(() => _localServices.StartAsync());

    private async void StopServiceButton_Click(object sender, RoutedEventArgs e) =>
        await RunServiceActionAsync(() => _localServices.StopAsync());

    private async Task RunServiceActionAsync(Func<Task<string>> action)
    {
        try { LocalServiceStatus.Text = "正在处理…"; LocalServiceStatus.Text = await action(); }
        catch (Exception exception) { LocalServiceStatus.Text = FriendlyError(exception); }
    }

    private async void BackupButton_Click(object sender, RoutedEventArgs e)
    {
        using var dialog = new Forms.FolderBrowserDialog { Description = "选择 JobFlow 备份保存位置", UseDescriptionForTitle = true };
        if (dialog.ShowDialog() == Forms.DialogResult.OK)
            await RunServiceActionAsync(() => _localServices.BackupAsync(dialog.SelectedPath));
    }

    private async void CheckUpdateButton_Click(object sender, RoutedEventArgs e)
    {
        try { WorkspaceStatus.Text = await UpdateChecker.CheckAsync(_settings.UpdateFeedUrl); }
        catch (Exception exception) { WorkspaceStatus.Text = $"检查更新失败：{FriendlyError(exception)}"; }
    }

    private void DarkModeInput_Click(object sender, RoutedEventArgs e)
    {
        var theme = DarkModeInput.IsChecked == true ? "Dark" : "Light";
        _settings = _settings with { Theme = theme };
        _settings.Save();
        ApplyTheme(theme);
    }

    private static void ApplyTheme(string theme)
    {
        var dark = theme == "Dark";
        SetBrush("CanvasBrush", dark ? "#171B18" : "#F5F4EF");
        SetBrush("SurfaceBrush", dark ? "#202521" : "#FFFEFA");
        SetBrush("SurfaceMutedBrush", dark ? "#282E29" : "#FAF9F5");
        SetBrush("InkBrush", dark ? "#EDF0EA" : "#252722");
        SetBrush("MutedBrush", dark ? "#AAB2AC" : "#777970");
        SetBrush("BorderBrush", dark ? "#3A423C" : "#DFDED7");
    }

    private static void SetBrush(string key, string color)
    {
        var converted = (System.Windows.Media.Color)System.Windows.Media.ColorConverter.ConvertFromString(color);
        System.Windows.Application.Current.Resources[key] = new SolidColorBrush(converted);
    }

    private async void FirstRunDiagnose_Click(object sender, RoutedEventArgs e)
    {
        FirstRunStatus.Text = "正在检测…";
        FirstRunStatus.Text = await _localServices.DiagnoseAsync();
    }

    private async void FirstRunStart_Click(object sender, RoutedEventArgs e)
    {
        try { FirstRunStatus.Text = await _localServices.StartAsync(); }
        catch (Exception exception) { FirstRunStatus.Text = FriendlyError(exception); }
    }

    private void FinishFirstRun_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var url = DesktopSettings.NormalizeApiUrl(FirstRunApiUrl.Text);
            _settings = _settings with { ApiBaseUrl = url, FirstRunCompleted = true };
            _settings.Save();
            LoginApiUrlInput.Text = SettingsApiUrlInput.Text = url;
            _api.Dispose(); _api = new ApiClient(url);
            FirstRunPanel.Visibility = Visibility.Collapsed;
            LoginStatus.Text = "设置完成，可以创建账户或直接登录。";
        }
        catch (Exception exception) { FirstRunStatus.Text = FriendlyError(exception); }
    }

    private void PasteUrlButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var text = System.Windows.Clipboard.GetText().Trim();
            if (!Uri.TryCreate(text, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https"))
                throw new FormatException("剪贴板中没有有效的 HTTP 或 HTTPS 链接。");
            SourceUrlInput.Text = text;
        }
        catch (Exception exception) { ComposerStatus.Text = FriendlyError(exception); }
    }

    private void NoteTemplate_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (sender is System.Windows.Controls.ComboBox { SelectedIndex: > 0, SelectedItem: ComboBoxItem item }) NotesInput.Text = item.Content?.ToString() ?? "";
    }

    private void InitializeHotkey()
    {
        try
        {
            _globalHotkey = new GlobalHotkey(this);
            _globalHotkey.Pressed += () => { RestoreWindow(); Composer.Visibility = Visibility.Visible; CompanyInput.Focus(); };
        }
        catch (Exception exception) { LoginStatus.Text = exception.Message; }
    }

    private void StartWithWindowsInput_Click(object sender, RoutedEventArgs e)
    {
        try { StartupManager.SetEnabled(StartWithWindowsInput.IsChecked == true); WorkspaceStatus.Text = StartWithWindowsInput.IsChecked == true ? "已开启开机自动启动" : "已关闭开机自动启动"; }
        catch (Exception exception) { StartWithWindowsInput.IsChecked = StartupManager.IsEnabled; WorkspaceStatus.Text = FriendlyError(exception); }
    }

    private async void ChangePasswordButton_Click(object sender, RoutedEventArgs e)
    {
        if (NewPasswordInput.Password.Length < 8) { WorkspaceStatus.Text = "新密码至少需要 8 位"; return; }
        await RunUiActionAsync(async () => { await _api.ChangePasswordAsync(CurrentPasswordInput.Password, NewPasswordInput.Password); CurrentPasswordInput.Clear(); NewPasswordInput.Clear(); }, "密码已修改");
    }

    private void LogoutButton_Click(object sender, RoutedEventArgs e) => LogoutToLogin(_api.BaseUrl, "已退出登录");
    private async void DeleteAccountButton_Click(object sender, RoutedEventArgs e)
    {
        if (MessageBox.Show("确定永久删除账户及全部数据吗？此操作无法撤销。", "删除账户", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes) return;
        await RunUiActionAsync(async () => { await _api.DeleteAccountAsync(); LogoutToLogin(_api.BaseUrl, "账户已删除"); });
    }

    private void LogoutToLogin(string apiUrl, string message)
    {
        _notificationTimer.Stop();
        _api.Dispose();
        _settings = new DesktopSettings(apiUrl);
        _api = new ApiClient(apiUrl);
        LoginApiUrlInput.Text = apiUrl;
        PasswordInput.Clear();
        Workspace.Visibility = Visibility.Collapsed;
        LoginPanel.Visibility = Visibility.Visible;
        LoginStatus.Text = message;
    }

    private async Task RunUiActionAsync(Func<Task> action, string success = "")
    {
        WorkspaceStatus.Text = "正在处理…";
        try { await action(); WorkspaceStatus.Text = success; ConnectionStatus.Text = "API 已连接"; }
        catch (Exception exception) { WorkspaceStatus.Text = FriendlyError(exception); if (exception is HttpRequestException or TaskCanceledException) ConnectionStatus.Text = "API 离线"; }
    }

    private static string SelectedStatus(System.Windows.Controls.ComboBox comboBox) =>
        (comboBox.SelectedItem as ComboBoxItem)?.Tag as string ?? "saved";
    private static string? EmptyToNull(string value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    private static DateTimeOffset? ParseOptionalDate(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        if (!DateTime.TryParse(value.Trim(), out var parsed)) throw new FormatException("下一步时间格式应为 yyyy-MM-dd HH:mm");
        return new DateTimeOffset(parsed);
    }

    private void ClearComposer()
    {
        CompanyInput.Clear(); TitleInput.Clear(); LocationInput.Clear(); SourceInput.Clear(); SourceUrlInput.Clear(); JdInput.Clear(); NotesInput.Clear(); NextActionInput.Clear(); CreateResumeInput.SelectedIndex = -1; CreateStatusInput.SelectedIndex = 0;
    }
    private void ClearApplicationEditor()
    {
        EditTitleInput.Clear(); EditCompanyInput.SelectedIndex = -1; EditLocationInput.Clear(); EditSourceInput.Clear(); EditSourceUrlInput.Clear(); EditJdInput.Clear(); EditNotesInput.Clear(); EditTagsInput.Clear(); EditCustomFieldsInput.Clear(); EditNextActionInput.Clear(); EditResumeInput.SelectedIndex = -1; EditStatusInput.SelectedIndex = -1; MatchResultText.Text = ""; _timeline.Clear(); _interviews.Clear();
    }
    private void ClearCompanyEditor() { CompanyNameInput.Clear(); CompanyWebsiteInput.Clear(); }

    private static string FriendlyError(Exception exception) => exception switch
    {
        ApiException api => api.Message,
        FormatException or ArgumentException => exception.Message,
        TaskCanceledException => "连接 API 超时，请检查服务器地址和网络",
        HttpRequestException => "无法连接 API，请检查服务器地址和网络",
        _ => $"操作失败：{exception.Message}",
    };

    private void RestoreWindow() { Show(); WindowState = WindowState.Normal; Activate(); }
    private void ExitApplication() { _explicitExit = true; _trayIcon.Visible = false; Close(); }
    private void MainWindow_Closing(object? sender, CancelEventArgs e)
    {
        if (!_explicitExit) { e.Cancel = true; Hide(); _trayIcon.ShowBalloonTip(2500, "JobFlow", "应用仍在托盘中运行提醒", Forms.ToolTipIcon.Info); return; }
        _notificationTimer.Stop(); _trayIcon.Dispose(); _globalHotkey?.Dispose(); _api.Dispose();
    }
}
