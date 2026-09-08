import {
  ArrowRight,
  Archive,
  ArchiveRestore,
  BarChart3,
  Bell,
  CalendarClock,
  Clock3,
  Download,
  ExternalLink,
  FileText,
  Inbox,
  LayoutDashboard,
  LogOut,
  MapPin,
  MoreHorizontal,
  Plus,
  Search,
  Sparkles,
  Target,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  Application,
  ApplicationStatus,
  clearToken,
  Company,
  DashboardInsights,
  downloadResume,
  FunnelItem,
  hasToken,
  InterviewRound,
  MatchResult,
  NotificationItem,
  ResumeVersion,
  TimelineEvent,
} from "./api";
import { AuthScreen } from "./components/AuthScreen";
import { columns, friendlyError } from "./ui";

type NewApplicationPayload = {
  company: string;
  title: string;
  location: string;
  sourceUrl: string;
  resumeId: string;
  notes: string;
  jdText: string;
  nextActionAt: string;
};

function readCaptureDraft(): Partial<NewApplicationPayload> | null {
  const params = new URLSearchParams(window.location.search);
  if (params.get("capture") !== "1") return null;
  return {
    company: params.get("company") ?? "",
    title: params.get("title") ?? "",
    sourceUrl: params.get("url") ?? "",
    jdText: params.get("jd") ?? "",
  };
}

function NewApplicationModal({
  companies,
  resumes,
  onClose,
  onCreated,
  initial,
}: {
  companies: Company[];
  resumes: ResumeVersion[];
  onClose: () => void;
  onCreated: () => Promise<void>;
  initial?: Partial<NewApplicationPayload>;
}) {
  const [form, setForm] = useState<NewApplicationPayload>({
    company: "",
    title: "",
    location: "",
    sourceUrl: "",
    resumeId: "",
    notes: "",
    jdText: "",
    nextActionAt: "",
    ...initial,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const noteTemplates = ["", "已投递，等待反馈", "需要准备系统设计与项目复盘", "一周后礼貌跟进"];

  function update(key: keyof NewApplicationPayload, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextActionValue = String(new FormData(event.currentTarget).get("nextActionAt") ?? "");
    setSubmitting(true);
    setError("");
    try {
      let company = companies.find(
        (item) => item.name.trim().toLocaleLowerCase() === form.company.trim().toLocaleLowerCase(),
      );
      if (!company) company = await api.createCompany({ name: form.company.trim() });
      let source = "manual";
      if (form.sourceUrl.trim()) {
        try { source = new URL(form.sourceUrl.trim()).hostname.replace(/^www\./, ""); } catch { source = "web"; }
      }
      const job = await api.createJob({
        company_id: company.id,
        title: form.title.trim(),
        location: form.location.trim() || undefined,
        source_url: form.sourceUrl.trim() || undefined,
        source,
        jd_text: form.jdText.trim() || undefined,
      });
      await api.createApplication({
        job_id: job.id,
        resume_version_id: form.resumeId ? Number(form.resumeId) : undefined,
        notes: form.notes.trim() || undefined,
        next_action_at: nextActionValue ? new Date(nextActionValue).toISOString() : undefined,
      });
      await onCreated();
      onClose();
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-application-title" onMouseDown={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <div>
            <p className="eyebrow">新的机会</p>
            <h2 id="new-application-title">记录一条投递</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="关闭"><X size={20} /></button>
        </header>
        <form onSubmit={submit} className="modal-form">
          <div className="form-grid">
            <label><span>公司名称 *</span><input value={form.company} onChange={(e) => update("company", e.target.value)} list="company-options" placeholder="例如：Example Labs" required /></label>
            <datalist id="company-options">{companies.map((company) => <option value={company.name} key={company.id} />)}</datalist>
            <label><span>岗位名称 *</span><input value={form.title} onChange={(e) => update("title", e.target.value)} placeholder="例如：后端开发实习生" required /></label>
            <label><span>地点</span><input value={form.location} onChange={(e) => update("location", e.target.value)} placeholder="上海 / 远程" /></label>
            <label><span>简历版本</span><select value={form.resumeId} onChange={(e) => update("resumeId", e.target.value)}><option value="">暂不关联</option>{resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.name}</option>)}</select></label>
            <label><span>下一步时间</span><input name="nextActionAt" type="datetime-local" value={form.nextActionAt} onChange={(e) => update("nextActionAt", e.target.value)} /></label>
          </div>
          <label><span>岗位链接</span><input type="url" value={form.sourceUrl} onChange={(e) => update("sourceUrl", e.target.value)} placeholder="https://…" /></label>
          <div className="inline-actions"><label className="grow"><span>常用备注模板</span><select onChange={(e) => { if (e.target.value) update("notes", e.target.value); }}><option value="">选择模板</option>{noteTemplates.slice(1).map((item) => <option key={item}>{item}</option>)}</select></label><button type="button" className="secondary-button clipboard-button" onClick={async () => { try { const text = await navigator.clipboard.readText(); if (/^https?:\/\//i.test(text.trim())) update("sourceUrl", text.trim()); else setError("剪贴板中没有可用的 HTTP 链接"); } catch { setError("无法读取剪贴板，请检查浏览器权限"); } }}>读取剪贴板链接</button></div>
          <label><span>备注</span><textarea value={form.notes} onChange={(e) => update("notes", e.target.value)} placeholder="内推人、截止日期或准备重点" rows={3} /></label>
          <label><span>JD 文本</span><textarea value={form.jdText} onChange={(e) => update("jdText", e.target.value)} placeholder="粘贴岗位职责和任职要求，浏览器扩展可自动带入" rows={5} /></label>
          {error && <p className="form-error">{error}</p>}
          <footer className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>取消</button>
            <button className="primary-button" disabled={submitting}>{submitting ? "正在保存…" : "保存到待投递"}</button>
          </footer>
        </form>
      </section>
    </div>
  );
}

export function ResumeModal({
  resumes,
  onClose,
  onCreated,
}: {
  resumes: ResumeVersion[];
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [contentText, setContentText] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setError("");
    setSubmitting(true);
    try {
      if (file) await api.uploadResume(name.trim(), file);
      else await api.createResume({ name: name.trim(), content_text: contentText.trim() || undefined });
      await onCreated();
      setName("");
      setFile(null);
      setContentText("");
      form.reset();
      setError("");
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setSubmitting(false);
    }
  }

  async function rename(resume: ResumeVersion) {
    const nextName = window.prompt("新的版本名称", resume.name)?.trim();
    if (!nextName || nextName === resume.name) return;
    setError("");
    try {
      await api.renameResume(resume.id, nextName);
      await onCreated();
    } catch (caught) {
      setError(friendlyError(caught));
    }
  }

  async function remove(resume: ResumeVersion) {
    if (!window.confirm(`确定删除简历版本“${resume.name}”吗？`)) return;
    setError("");
    try {
      await api.deleteResume(resume.id);
      await onCreated();
    } catch (caught) {
      setError(friendlyError(caught));
    }
  }

  async function editText(resume: ResumeVersion) {
    const text = window.prompt("粘贴用于本地匹配的简历文本", resume.content_text ?? "");
    if (text === null) return;
    try { await api.updateResumeText(resume.id, resume.name, text); await onCreated(); }
    catch (caught) { setError(friendlyError(caught)); }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal modal--compact" role="dialog" aria-modal="true" onMouseDown={(e) => e.stopPropagation()}>
        <header className="modal-header"><div><p className="eyebrow">材料管理</p><h2>简历版本</h2></div><button className="icon-button" onClick={onClose}><X size={20} /></button></header>
        <div className="resume-list">
          {resumes.length === 0 ? <p className="resume-empty">还没有简历版本</p> : resumes.map((resume) => (
            <div className="resume-row" key={resume.id}>
              <span className="resume-file-icon"><FileText size={17} /></span>
              <div><strong>{resume.name}</strong><small>{resume.file_name ?? "仅版本记录"}</small></div>
              {resume.has_file && <button type="button" className="download-button" aria-label={`下载 ${resume.name}`} onClick={async () => { try { await downloadResume(resume); } catch (caught) { setError(friendlyError(caught)); } }}><Download size={16} /></button>}
              <button type="button" className="download-button" aria-label={`编辑 ${resume.name} 文本`} onClick={() => void editText(resume)}>文</button>
              <button type="button" className="download-button" aria-label={`重命名 ${resume.name}`} onClick={() => void rename(resume)}>改</button>
              <button type="button" className="download-button danger-button" aria-label={`删除 ${resume.name}`} onClick={() => void remove(resume)}><Trash2 size={15} /></button>
            </div>
          ))}
        </div>
        <form onSubmit={submit} className="modal-form">
          <p className="form-section-title">添加新版本</p>
          <label><span>版本名称 *</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="后端实习 v1" required /></label>
          <label><span>简历文件</span><input className="file-input" type="file" accept=".pdf,.doc,.docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
          {!file && <label><span>可分析文本（仅本地规则匹配）</span><textarea rows={6} value={contentText} onChange={(e) => setContentText(e.target.value)} placeholder="粘贴简历正文；不会发送给第三方 AI" /></label>}
          <p className="field-hint">支持 PDF、DOC 和 DOCX，单个文件不超过 5 MB。也可以先只创建版本名称。</p>
          {error && <p className="form-error">{error}</p>}
          <footer className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>取消</button><button className="primary-button" disabled={submitting}>{submitting ? "正在添加…" : "添加版本"}</button></footer>
        </form>
      </section>
    </div>
  );
}

function ApplicationCard({ application, selected, onSelect, onDragStart, onOpen }: { application: Application; selected: boolean; onSelect: () => void; onDragStart: () => void; onOpen: () => void }) {
  const { job } = application;
  return (
    <article className="application-card" draggable onDragStart={onDragStart} onClick={onOpen} onKeyDown={(event) => { if (event.key === "Enter") onOpen(); }} role="button" tabIndex={0}>
      <div className="card-topline">
        <span className="company-avatar">{job.company.name.slice(0, 1).toUpperCase()}</span>
        <input type="checkbox" checked={selected} aria-label={`选择 ${job.title}`} onClick={(event) => event.stopPropagation()} onChange={onSelect} />
        <button className="quiet-button" aria-label="查看详情" onClick={(event) => { event.stopPropagation(); onOpen(); }}><MoreHorizontal size={18} /></button>
      </div>
      <div className="card-copy">
        <p className="company-name">{job.company.name}</p>
        <h3>{job.title}</h3>
      </div>
      <div className="card-meta">
        {job.location && <span><MapPin size={13} />{job.location}</span>}
        {application.resume_version && <span><FileText size={13} />{application.resume_version.name}</span>}
        {application.next_action_at && <span><CalendarClock size={13} />{new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(application.next_action_at))}</span>}
      </div>
      <footer className="card-footer">
        <span>{new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(application.updated_at))}</span>
        {job.source_url && <a href={job.source_url} target="_blank" rel="noreferrer" aria-label="打开岗位链接"><ExternalLink size={14} /></a>}
      </footer>
    </article>
  );
}

const statusLabel = Object.fromEntries(columns.map((column) => [column.key, column.label]));

function ApplicationDetailModal({ application, applications, companies, resumes, onClose, onChanged }: { application: Application; applications: Application[]; companies: Company[]; resumes: ResumeVersion[]; onClose: () => void; onChanged: () => Promise<void> }) {
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [error, setError] = useState("");
  const [notes, setNotes] = useState(application.notes ?? "");
  const [resumeId, setResumeId] = useState(application.resume_version_id?.toString() ?? "");
  const [nextActionAt, setNextActionAt] = useState(() => application.next_action_at ? new Date(application.next_action_at).toISOString().slice(0, 16) : "");
  const [saving, setSaving] = useState(false);
  const [companyId, setCompanyId] = useState(application.job.company_id.toString());
  const [jobTitle, setJobTitle] = useState(application.job.title);
  const [location, setLocation] = useState(application.job.location ?? "");
  const [sourceUrl, setSourceUrl] = useState(application.job.source_url ?? "");
  const [jdText, setJdText] = useState(application.job.jd_text ?? "");
  const [tags, setTags] = useState((application.tags ?? []).join(", "));
  const [customFields, setCustomFields] = useState(Object.entries(application.custom_fields ?? {}).map(([key, value]) => `${key}: ${value}`).join("\n"));
  const [interviews, setInterviews] = useState<InterviewRound[]>([]);
  const [match, setMatch] = useState<MatchResult | null>(null);
  const [roundName, setRoundName] = useState("一面");
  const [roundAt, setRoundAt] = useState("");

  useEffect(() => {
    Promise.all([api.timeline(application.id), api.interviews(application.id)])
      .then(([events, rounds]) => { setTimeline(events); setInterviews(rounds); })
      .catch((caught) => setError(friendlyError(caught)));
  }, [application.id]);

  async function saveDetails(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.updateJob(application.job.id, {
        company_id: Number(companyId),
        title: jobTitle.trim(),
        location: location.trim() || null,
        source_url: sourceUrl.trim() || null,
        jd_text: jdText.trim() || null,
      });
      await api.updateApplication(application.id, {
        notes: notes.trim() || null,
        resume_version_id: resumeId ? Number(resumeId) : null,
        next_action_at: nextActionAt ? new Date(nextActionAt).toISOString() : null,
        tags: tags.split(",").map((item) => item.trim()).filter(Boolean),
        custom_fields: Object.fromEntries(customFields.split("\n").map((line) => line.split(":")).filter((parts) => parts.length > 1).map(([key, ...value]) => [key.trim(), value.join(":").trim()])),
      });
      await onChanged();
      onClose();
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setSaving(false);
    }
  }

  async function addInterview() {
    if (!roundAt) { setError("请选择面试时间"); return; }
    setSaving(true); setError("");
    try {
      await api.createInterview(application.id, { round_name: roundName.trim(), interview_type: "video", scheduled_at: new Date(roundAt).toISOString(), duration_minutes: 60, location: null, interviewer: null, notes: null });
      setInterviews(await api.interviews(application.id)); await onChanged(); setRoundAt("");
    } catch (caught) { setError(friendlyError(caught)); } finally { setSaving(false); }
  }

  async function removeApplication() {
    if (!window.confirm(`确定删除“${application.job.title}”的投递和岗位记录吗？此操作不可撤销。`)) return;
    setSaving(true);
    setError("");
    try {
      await api.deleteApplication(application.id);
      await api.deleteJob(application.job.id);
      await onChanged();
      onClose();
    } catch (caught) {
      setError(friendlyError(caught));
      setSaving(false);
    }
  }

  async function archiveApplication() {
    setSaving(true);
    setError("");
    try {
      await api.archiveApplication(application.id);
      await onChanged();
      onClose();
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal detail-modal" role="dialog" aria-modal="true" aria-labelledby="application-detail-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="modal-header">
          <div><p className="eyebrow">{application.job.company.name}</p><h2 id="application-detail-title">{application.job.title}</h2></div>
          <button className="icon-button" onClick={onClose} aria-label="关闭"><X size={20} /></button>
        </header>
        <div className="detail-body">
          <div className="detail-summary">
            <span className={`detail-status detail-status--${application.status}`}>{statusLabel[application.status]}</span>
            {application.job.location && <span><MapPin size={14} />{application.job.location}</span>}
            {application.resume_version && <span><FileText size={14} />{application.resume_version.name}</span>}
            {application.job.source_url && <a href={application.job.source_url} target="_blank" rel="noreferrer">打开岗位页面 <ExternalLink size={13} /></a>}
          </div>
          <form className="detail-edit-form" onSubmit={saveDetails}>
            <label><span>公司</span><select value={companyId} onChange={(event) => setCompanyId(event.target.value)}>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label>
            <label><span>岗位名称</span><input value={jobTitle} onChange={(event) => setJobTitle(event.target.value)} required /></label>
            <label><span>地点</span><input value={location} onChange={(event) => setLocation(event.target.value)} /></label>
            <label><span>岗位链接</span><input type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} /></label>
            <label><span>关联简历</span><select value={resumeId} onChange={(event) => setResumeId(event.target.value)}><option value="">暂不关联</option>{resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.name}</option>)}</select></label>
            <label><span>下一步时间</span><input type="datetime-local" value={nextActionAt} onChange={(event) => setNextActionAt(event.target.value)} /></label>
            <label className="detail-notes"><span>投递备注</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} placeholder="记录联系人、准备重点或下一步" /></label>
            <label className="detail-notes"><span>岗位描述</span><textarea value={jdText} onChange={(event) => setJdText(event.target.value)} rows={5} /></label>
            <label className="detail-notes"><span>标签（逗号分隔）</span><input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="重点, 远程, 校招" /></label>
            <label className="detail-notes"><span>自定义字段（每行 键: 值）</span><textarea value={customFields} onChange={(event) => setCustomFields(event.target.value)} rows={3} placeholder="薪资范围: 25k-35k" /></label>
            <div className="detail-edit-actions"><div className="inline-actions"><button type="button" className="secondary-button" onClick={() => void archiveApplication()} disabled={saving}><Archive size={15} />归档</button><button type="button" className="secondary-button danger-text" onClick={() => void removeApplication()} disabled={saving}><Trash2 size={15} />删除</button></div><button className="primary-button" disabled={saving}>{saving ? "保存中…" : "保存修改"}</button></div>
          </form>
          <section className="productivity-panel">
            <header><h3>面试轮次</h3><button className="secondary-button" onClick={() => void api.exportCalendar()}>导出日历</button></header>
            {interviews.map((item) => <div className="interview-row" key={item.id}><div><strong>{item.round_name}</strong><small>{new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.scheduled_at))} · {item.duration_minutes} 分钟</small></div><select value={item.outcome ?? ""} onChange={async (e) => { await api.updateInterview(item.id, { outcome: e.target.value || null }); setInterviews(await api.interviews(application.id)); }}><option value="">待进行</option><option value="passed">通过</option><option value="failed">未通过</option><option value="cancelled">取消</option></select><button className="danger-text quiet-button" onClick={async () => { await api.deleteInterview(item.id); setInterviews(await api.interviews(application.id)); }}>删除</button></div>)}
            <div className="interview-create"><input value={roundName} onChange={(e) => setRoundName(e.target.value)} placeholder="轮次名称" /><input type="datetime-local" value={roundAt} onChange={(e) => setRoundAt(e.target.value)} /><button className="secondary-button" onClick={() => void addInterview()}>添加轮次</button></div>
          </section>
          <section className="productivity-panel">
            <header><h3>JD / 简历本地匹配</h3><button className="secondary-button" onClick={() => void api.matchApplication(application.id).then(setMatch).catch((caught) => setError(friendlyError(caught)))}>生成分析</button></header>
            {match && <div className="match-result"><strong>{match.score} 分</strong><p>{match.recommendation}</p><p><b>已匹配：</b>{match.matched_keywords.join("、") || "暂无"}</p><p><b>待补充：</b>{match.missing_keywords.join("、") || "暂无"}</p>{match.questions.map((question) => <small key={question}>{question}</small>)}</div>}
          </section>
          <section className="productivity-actions"><button className="secondary-button" onClick={async () => { try { await api.undoStatus(application.id); await onChanged(); onClose(); } catch (caught) { setError(friendlyError(caught)); } }}>撤销最近状态变化</button><select id={`merge-${application.id}`} defaultValue=""><option value="">选择重复投递…</option>{applications.filter((item) => item.id !== application.id).map((item) => <option key={item.id} value={item.id}>{item.job.company.name} · {item.job.title}</option>)}</select><button className="secondary-button" onClick={async () => { const select = document.getElementById(`merge-${application.id}`) as HTMLSelectElement; if (!select.value || !window.confirm("合并后重复记录会被删除，继续吗？")) return; try { await api.mergeApplication(application.id, Number(select.value)); await onChanged(); onClose(); } catch (caught) { setError(friendlyError(caught)); } }}>合并重复项</button></section>
          <div className="detail-grid detail-grid--single">
            <section><h3>岗位描述</h3><p className="jd-copy">{application.job.jd_text || "暂无 JD 文本，可通过浏览器扩展重新采集。"}</p></section>
          </div>
          <section className="timeline-panel">
            <h3><Clock3 size={16} />状态时间线</h3>
            {error && <p className="form-error">{error}</p>}
            {!error && timeline.length === 0 && <p className="timeline-empty">正在读取记录…</p>}
            {timeline.map((event) => (
              <div className="timeline-row" key={event.id}>
                <span className="timeline-dot" />
                <div>
                  <strong>{event.event_type === "application_created" ? "创建投递" : `状态更新为 ${statusLabel[event.to_status as ApplicationStatus] ?? event.to_status}`}</strong>
                  <small>{new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(event.created_at))}</small>
                </div>
              </div>
            ))}
          </section>
        </div>
      </section>
    </div>
  );
}

function EmptyColumn() {
  return <div className="empty-column"><Inbox size={18} /><span>拖到这里</span></div>;
}

function ScheduleView({ applications, onOpen }: { applications: Application[]; onOpen: (application: Application) => void }) {
  const [now] = useState(() => Date.now());
  const [mode, setMode] = useState<"week" | "month">("week");
  const scheduled = applications
    .filter((application) => application.next_action_at)
    .filter((application) => new Date(application.next_action_at!).getTime() <= now + (mode === "week" ? 7 : 31) * 86400000)
    .sort((a, b) => new Date(a.next_action_at!).getTime() - new Date(b.next_action_at!).getTime());

  if (scheduled.length === 0) {
    return <section className="empty-view"><span><CalendarClock size={23} /></span><h2>还没有待办日程</h2><p>新建投递时设置“下一步时间”，面试、笔试和跟进事项会集中显示在这里。</p></section>;
  }

  return (
    <section className="schedule-view">
      <header className="section-heading"><div><p className="eyebrow">Next actions</p><h2>接下来的安排</h2></div><div className="inline-actions"><button className={mode === "week" ? "secondary-button active" : "secondary-button"} onClick={() => setMode("week")}>周视图</button><button className={mode === "month" ? "secondary-button active" : "secondary-button"} onClick={() => setMode("month")}>月视图</button><button className="secondary-button" onClick={() => void api.exportCalendar()}><Download size={15} />ICS</button><span>{scheduled.length} 项</span></div></header>
      <div className="schedule-list">
        {scheduled.map((application) => {
          const due = new Date(application.next_action_at!);
          const overdue = due.getTime() < now;
          return (
            <button className="schedule-row" key={application.id} onClick={() => onOpen(application)}>
              <time className={overdue ? "schedule-date schedule-date--overdue" : "schedule-date"}><strong>{due.getDate()}</strong><span>{new Intl.DateTimeFormat("zh-CN", { month: "short" }).format(due)}</span></time>
              <div><span className="company-name">{application.job.company.name}</span><h3>{application.job.title}</h3><p>{overdue ? "已到时间，请更新进度" : new Intl.DateTimeFormat("zh-CN", { weekday: "long", hour: "2-digit", minute: "2-digit" }).format(due)}</p></div>
              <span className={`detail-status detail-status--${application.status}`}>{statusLabel[application.status]}</span>
              <ArrowRight size={17} />
            </button>
          );
        })}
      </div>
    </section>
  );
}

function ArchivedView({ applications, onRestore }: { applications: Application[]; onRestore: (id: number) => Promise<void> }) {
  if (applications.length === 0) {
    return <section className="empty-view"><span><Archive size={23} /></span><h2>归档为空</h2><p>暂时放下的机会可以从详情页归档，并随时在这里恢复。</p></section>;
  }
  return <section className="schedule-view"><header className="section-heading"><div><p className="eyebrow">Archive</p><h2>已归档投递</h2></div><span>{applications.length} 条</span></header><div className="schedule-list">{applications.map((application) => <div className="schedule-row" key={application.id}><span className="company-avatar">{application.job.company.name.slice(0, 1).toUpperCase()}</span><div><span className="company-name">{application.job.company.name}</span><h3>{application.job.title}</h3><p>{application.archived_at ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(application.archived_at)) : ""}</p></div><span className={`detail-status detail-status--${application.status}`}>{statusLabel[application.status]}</span><button className="secondary-button" onClick={() => void onRestore(application.id)}><ArchiveRestore size={15} />恢复</button></div>)}</div></section>;
}

function AnalyticsView({ applications, funnel, insights }: { applications: Application[]; funnel: FunnelItem[]; insights: DashboardInsights | null }) {
  const total = applications.length;
  const sources = Object.entries(applications.reduce<Record<string, number>>((result, application) => {
    const source = application.job.source || "手动录入";
    result[source] = (result[source] ?? 0) + 1;
    return result;
  }, {})).sort((a, b) => b[1] - a[1]);

  return (
    <section className="analytics-view">
      <header className="section-heading"><div><p className="eyebrow">Review</p><h2>当前投递分布</h2></div><span>基于 {total} 条真实记录</span></header>
      {insights && <div className="insight-summary"><div><span>Offer 到达率</span><strong>{insights.offer_rate}%</strong></div><div><span>历史进入面试</span><strong>{insights.stages.find((item) => item.status === "interview")?.ever_reached ?? 0}</strong></div><div><span>平均到 Offer</span><strong>{insights.average_days_to_offer === null ? "—" : `${insights.average_days_to_offer} 天`}</strong></div><div><span>活跃投递</span><strong>{insights.active_applications}</strong></div></div>}
      <div className="analytics-grid">
        <div className="analytics-card">
          <h3>阶段分布</h3>
          <div className="stage-bars">
            {funnel.map((item) => {
              const percentage = total ? Math.round((item.count / total) * 100) : 0;
              return <div className="stage-bar" key={item.status}><div><span>{statusLabel[item.status]}</span><strong>{item.count}</strong></div><div className="bar-track"><span className={`bar-fill bar-fill--${item.status}`} style={{ width: `${percentage}%` }} /></div><small>{percentage}%</small></div>;
            })}
          </div>
        </div>
        <div className="analytics-card">
          <h3>简历版本表现</h3>
          <div className="source-list">
            {!insights?.resumes.length ? <p className="timeline-empty">关联简历后显示版本表现</p> : insights.resumes.map((item, index) => <div className="source-row" key={item.resume}><span className="source-rank">{String(index + 1).padStart(2, "0")}</span><div><strong>{item.resume}</strong><small>{item.interviews} 次进入面试 · {item.offers} 个 Offer</small></div><b>{item.total}</b></div>)}
          </div>
        </div>
        <div className="analytics-card">
          <h3>近 12 周投递趋势</h3>
          <div className="trend-bars">
            {!insights?.weekly_trend.length ? <p className="timeline-empty">暂无趋势数据</p> : insights.weekly_trend.map((item) => { const maximum = Math.max(...insights.weekly_trend.map((week) => week.applications), 1); return <div className="trend-item" key={item.week} title={`${item.week}: ${item.applications} 条`}><span style={{ height: `${Math.max(8, item.applications / maximum * 100)}%` }} /><small>{item.week.slice(5)}</small></div>; })}
          </div>
        </div>
        <div className="analytics-card">
          <h3>岗位来源</h3>
          <div className="source-list">
            {sources.length === 0 ? <p className="timeline-empty">添加投递后显示来源分布</p> : sources.map(([source, count], index) => (
              <div className="source-row" key={source}><span className="source-rank">{String(index + 1).padStart(2, "0")}</span><div><strong>{source}</strong><small>{insights?.sources.find((item) => item.source === source)?.interviews ?? 0} 次进入面试 · {insights?.sources.find((item) => item.source === source)?.offers ?? 0} 个 Offer</small></div><b>{count}</b></div>
            ))}
          </div>
        </div>
      </div>
      <p className="analytics-note">到达率与耗时只根据真实状态时间线计算；跳过的阶段不会被推断为已到达。</p>
    </section>
  );
}

function NotificationPanel({ notifications, onClose, onRead }: { notifications: NotificationItem[]; onClose: () => void; onRead: (id: number) => Promise<void> }) {
  return <div className="notification-panel"><header><strong>提醒中心</strong><button className="icon-button" onClick={onClose} aria-label="关闭提醒"><X size={17} /></button></header>{notifications.length === 0 ? <p className="timeline-empty">暂时没有提醒</p> : notifications.map((item) => <button key={item.id} className={`notification-row ${item.read_at ? "" : "notification-row--unread"}`} onClick={() => void onRead(item.id)}><strong>{item.title}</strong><span>{item.body}</span><small>{new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(item.scheduled_for))}</small></button>)}</div>;
}

function Dashboard({ onLogout }: { onLogout: () => void }) {
  const [captureAtMount] = useState(readCaptureDraft);
  const [view, setView] = useState<"board" | "schedule" | "analytics" | "archive">("board");
  const [applications, setApplications] = useState<Application[]>([]);
  const [archivedApplications, setArchivedApplications] = useState<Application[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [resumes, setResumes] = useState<ResumeVersion[]>([]);
  const [funnel, setFunnel] = useState<FunnelItem[]>([]);
  const [insights, setInsights] = useState<DashboardInsights | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [newApplicationOpen, setNewApplicationOpen] = useState(Boolean(captureAtMount));
  const [resumeOpen, setResumeOpen] = useState(false);
  const [captureDraft, setCaptureDraft] = useState<Partial<NewApplicationPayload>>(captureAtMount ?? {});
  const [selectedApplication, setSelectedApplication] = useState<Application | null>(null);
  const [draggedId, setDraggedId] = useState<number | null>(null);
  const [moving, setMoving] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [dark, setDark] = useState(() => localStorage.getItem("jobflow_theme") === "dark");

  const loadData = useCallback(async () => {
    try {
      const [applicationData, archivedData, companyData, resumeData, funnelData, insightData, notificationData] = await Promise.all([
        api.applications(), api.applications(true), api.companies(), api.resumes(), api.funnel(), api.insights(), api.notifications(),
      ]);
      setApplications(applicationData);
      setArchivedApplications(archivedData);
      setCompanies(companyData);
      setResumes(resumeData);
      setFunnel(funnelData);
      setInsights(insightData);
      setNotifications(notificationData);
      setError("");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        clearToken();
        onLogout();
        return;
      }
      setError(friendlyError(caught));
    } finally {
      setLoading(false);
    }
  }, [onLogout]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData]);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("jobflow_theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "n") { event.preventDefault(); setNewApplicationOpen(true); }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return applications;
    return applications.filter((application) =>
      `${application.job.title} ${application.job.company.name} ${application.job.location ?? ""}`
        .toLocaleLowerCase().includes(needle),
    );
  }, [applications, query]);

  async function dropInto(status: ApplicationStatus) {
    if (draggedId === null) return;
    const current = applications.find((item) => item.id === draggedId);
    if (!current || current.status === status) { setDraggedId(null); return; }
    const snapshot = applications;
    setApplications((items) => items.map((item) => item.id === draggedId ? { ...item, status } : item));
    setMoving(draggedId);
    try {
      await api.moveApplication(draggedId, status);
      await loadData();
    } catch (caught) {
      setApplications(snapshot);
      setError(friendlyError(caught));
    } finally {
      setMoving(null);
      setDraggedId(null);
    }
  }

  const funnelMap = Object.fromEntries(funnel.map((item) => [item.status, item.count]));
  const activeCount = applications.filter((item) => !["offer", "closed"].includes(item.status)).length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><ArrowRight size={18} /></span><span>JobFlow</span></div>
        <nav>
          <button className={`nav-item ${view === "board" ? "nav-item--active" : ""}`} onClick={() => setView("board")}><LayoutDashboard size={18} /><span>投递看板</span></button>
          <button className="nav-item" onClick={() => setResumeOpen(true)}><FileText size={18} /><span>简历版本</span><small>{resumes.length}</small></button>
          <button className={`nav-item ${view === "schedule" ? "nav-item--active" : ""}`} onClick={() => setView("schedule")}><CalendarClock size={18} /><span>面试日程</span></button>
          <button className={`nav-item ${view === "analytics" ? "nav-item--active" : ""}`} onClick={() => setView("analytics")}><BarChart3 size={18} /><span>数据复盘</span></button>
          <button className={`nav-item ${view === "archive" ? "nav-item--active" : ""}`} onClick={() => setView("archive")}><Archive size={18} /><span>归档</span><small>{archivedApplications.length}</small></button>
        </nav>
        <div className="sidebar-tip">
          <Sparkles size={17} />
          <div><strong>保持真实记录</strong><p>每次状态变化都会进入时间线。</p></div>
        </div>
        <button className="logout-button" onClick={() => { clearToken(); onLogout(); }}><LogOut size={17} /><span>退出登录</span></button>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div><p className="breadcrumb">工作区 <span>/</span> 我的求职</p><h1>{view === "board" ? "投递看板" : view === "schedule" ? "面试日程" : view === "analytics" ? "数据复盘" : "投递归档"}</h1></div>
          <div className="topbar-actions">
            {view === "board" && <label className="search-box"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索公司或岗位" /></label>}
            <button className="notification-button" aria-label="提醒" onClick={() => setNotificationsOpen((current) => !current)}><Bell size={17} />{notifications.some((item) => !item.read_at) && <span />}</button>
            <button className="notification-button" aria-label="切换深色模式" title="深色模式" onClick={() => setDark((value) => !value)}>{dark ? "☀" : "☾"}</button>
            <button className="secondary-button export-button" onClick={() => { void api.exportApplications().catch((caught) => setError(friendlyError(caught))); }}><Download size={16} />导出 CSV</button>
            <button className="secondary-button export-button" onClick={() => { void api.exportApplicationsJson().catch((caught) => setError(friendlyError(caught))); }}><Download size={16} />JSON</button>
            <label className="secondary-button export-button import-button"><Upload size={16} />导入 CSV<input type="file" accept=".csv,text/csv" onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; void api.importApplications(file).then(async (result) => { await loadData(); window.alert(`导入 ${result.imported} 条，跳过 ${result.skipped} 条，错误 ${result.errors.length} 条`); }).catch((caught) => setError(friendlyError(caught))); event.currentTarget.value = ""; }} /></label>
            <button className="primary-button" onClick={() => setNewApplicationOpen(true)}><Plus size={17} />新建投递</button>
          </div>
        </header>

        <section className="summary-row">
          <div className="summary-copy"><span className="summary-icon"><Target size={20} /></span><div><p>进行中的机会</p><strong>{activeCount}</strong></div></div>
          <div className="summary-divider" />
          <div className="mini-stat"><span>已投递</span><strong>{funnelMap.applied ?? 0}</strong></div>
          <div className="mini-stat"><span>面试中</span><strong>{funnelMap.interview ?? 0}</strong></div>
          <div className="mini-stat mini-stat--accent"><span>Offer</span><strong>{funnelMap.offer ?? 0}</strong></div>
          <div className="summary-note"><span className="live-dot" />数据实时更新</div>
        </section>

        {error && <div className="banner-error"><span>{error}</span><button onClick={() => { setError(""); void loadData(); }}>重试</button></div>}
        {selectedIds.length > 0 && <div className="batch-toolbar"><strong>已选 {selectedIds.length} 条</strong><select defaultValue="" onChange={async (event) => { if (!event.target.value) return; try { await api.bulkStatus(selectedIds, event.target.value as ApplicationStatus); setSelectedIds([]); await loadData(); } catch (caught) { setError(friendlyError(caught)); } }}><option value="">批量修改状态…</option>{columns.map((column) => <option key={column.key} value={column.key}>{column.label}</option>)}</select><button className="quiet-button" onClick={() => setSelectedIds([])}>清除选择</button></div>}

        {view === "board" && <section className="board" aria-busy={loading}>
          {columns.map((column) => {
            const items = filtered.filter((application) => application.status === column.key);
            return (
              <div className="board-column" key={column.key} onDragOver={(e) => e.preventDefault()} onDrop={() => void dropInto(column.key)}>
                <header className="column-header"><div><span className={`status-dot status-dot--${column.key}`} /><strong>{column.label}</strong><small>{items.length}</small></div><span>{column.hint}</span></header>
                <div className={`column-cards ${draggedId !== null ? "column-cards--receiving" : ""}`}>
                  {loading ? <div className="card-skeleton" /> : items.length ? items.map((application) => <ApplicationCard key={application.id} application={application} selected={selectedIds.includes(application.id)} onSelect={() => setSelectedIds((ids) => ids.includes(application.id) ? ids.filter((id) => id !== application.id) : [...ids, application.id])} onDragStart={() => setDraggedId(application.id)} onOpen={() => setSelectedApplication(application)} />) : <EmptyColumn />}
                  {moving !== null && items.some((item) => item.id === moving) && <div className="moving-indicator">正在保存…</div>}
                </div>
              </div>
            );
          })}
        </section>}
        {view === "board" && !loading && applications.length === 0 && <section className="empty-view workspace-empty"><span><Sparkles size={23} /></span><h2>从一条示例投递开始</h2><p>示例包含标签、自定义字段、日程和本地匹配文本，可随时删除。</p><button className="primary-button" onClick={() => void api.createSampleData().then(loadData).catch((caught) => setError(friendlyError(caught)))}>创建示例数据</button></section>}
        {view === "schedule" && <ScheduleView applications={applications} onOpen={setSelectedApplication} />}
        {view === "analytics" && <AnalyticsView applications={applications} funnel={funnel} insights={insights} />}
        {view === "archive" && <ArchivedView applications={archivedApplications} onRestore={async (id) => { await api.restoreApplication(id); await loadData(); }} />}
      </main>

      {notificationsOpen && <NotificationPanel notifications={notifications} onClose={() => setNotificationsOpen(false)} onRead={async (id) => { await api.markNotificationRead(id); await loadData(); }} />}

      {newApplicationOpen && <NewApplicationModal companies={companies} resumes={resumes} initial={captureDraft} onClose={() => { setNewApplicationOpen(false); setCaptureDraft({}); window.history.replaceState({}, "", window.location.pathname); }} onCreated={loadData} />}
      {resumeOpen && <ResumeModal resumes={resumes} onClose={() => setResumeOpen(false)} onCreated={loadData} />}
      {selectedApplication && <ApplicationDetailModal application={selectedApplication} applications={applications} companies={companies} resumes={resumes} onChanged={loadData} onClose={() => setSelectedApplication(null)} />}
    </div>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(hasToken());
  return authenticated
    ? <Dashboard onLogout={() => setAuthenticated(false)} />
    : <AuthScreen onAuthenticated={() => setAuthenticated(true)} />;
}
