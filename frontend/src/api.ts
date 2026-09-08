export type ApplicationStatus =
  | "saved"
  | "applied"
  | "assessment"
  | "interview"
  | "offer"
  | "closed";

export type Company = {
  id: number;
  name: string;
  website: string | null;
};

export type ResumeVersion = {
  id: number;
  name: string;
  file_name: string | null;
  has_file: boolean;
  content_text?: string | null;
  created_at: string;
};

export type TimelineEvent = {
  id: number;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  created_at: string;
};

export type Job = {
  id: number;
  company_id: number;
  title: string;
  location: string | null;
  source: string | null;
  source_url: string | null;
  jd_text: string | null;
  created_at: string;
  company: Company;
};

export type Application = {
  id: number;
  job_id: number;
  resume_version_id: number | null;
  status: ApplicationStatus;
  notes: string | null;
  applied_at: string | null;
  next_action_at: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  tags: string[];
  custom_fields: Record<string, string>;
  job: Job;
  resume_version: ResumeVersion | null;
};

export type InterviewRound = {
  id: number; application_id: number; round_name: string; interview_type: string;
  scheduled_at: string; duration_minutes: number; location: string | null;
  interviewer: string | null; notes: string | null; outcome: string | null;
  created_at: string; updated_at: string;
};

export type MatchResult = {
  score: number; matched_keywords: string[]; missing_keywords: string[];
  questions: string[]; recommendation: string;
};

export type FunnelItem = { status: ApplicationStatus; count: number };

export type NotificationItem = {
  id: number;
  application_id: number | null;
  kind: string;
  title: string;
  body: string;
  scheduled_for: string;
  delivered_at: string | null;
  read_at: string | null;
  created_at: string;
};

export type DashboardInsights = {
  total_applications: number;
  active_applications: number;
  offer_rate: number;
  average_days_to_offer: number | null;
  stages: Array<{
    status: ApplicationStatus;
    current_count: number;
    ever_reached: number;
    average_days_to_reach: number | null;
  }>;
  sources: Array<{ source: string; total: number; interviews: number; offers: number }>;
  resumes: Array<{ resume: string; total: number; interviews: number; offers: number }>;
  weekly_trend: Array<{ week: string; applications: number }>;
};

export type CSVImportResult = {
  imported: number;
  skipped: number;
  errors: Array<{ row: number; detail: string }>;
};

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
const TOKEN_KEY = "jobflow_access_token";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export function hasToken() {
  return Boolean(localStorage.getItem(TOKEN_KEY));
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export async function downloadResume(resume: ResumeVersion) {
  const token = localStorage.getItem(TOKEN_KEY);
  const response = await fetch(`${BASE_URL}/resumes/${resume.id}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "下载失败" }));
    throw new ApiError(body.detail ?? "下载失败", response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = resume.file_name ?? `${resume.name}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new ApiError(body.detail ?? "请求失败", response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function authenticatedDownload(path: string, filename: string) {
  const token = localStorage.getItem(TOKEN_KEY);
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "下载失败" }));
    throw new ApiError(body.detail ?? "下载失败", response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function authenticate(mode: "login" | "register", email: string, password: string) {
  const result = await request<{ access_token: string }>(`/auth/${mode}`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  localStorage.setItem(TOKEN_KEY, result.access_token);
}

export const api = {
  applications: (archived = false) =>
    request<Application[]>(`/applications?archived=${archived}`),
  companies: () => request<Company[]>("/companies"),
  resumes: () => request<ResumeVersion[]>("/resumes"),
  funnel: () => request<FunnelItem[]>("/dashboard/funnel"),
  insights: () => request<DashboardInsights>("/dashboard/insights"),
  notifications: (unreadOnly = false) =>
    request<NotificationItem[]>(`/notifications?unread_only=${unreadOnly}`),
  markNotificationRead: (id: number) =>
    request<NotificationItem>(`/notifications/${id}/read`, { method: "PATCH" }),
  exportApplications: () => authenticatedDownload("/applications-export.csv", "jobflow-applications.csv"),
  exportApplicationsJson: () => authenticatedDownload("/applications-export.json", "jobflow-applications.json"),
  exportCalendar: () => authenticatedDownload("/calendar.ics", "jobflow-calendar.ics"),
  importApplications: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<CSVImportResult>("/applications-import.csv", { method: "POST", body });
  },
  timeline: (applicationId: number) =>
    request<TimelineEvent[]>(`/applications/${applicationId}/timeline`),
  interviews: (applicationId: number) =>
    request<InterviewRound[]>(`/applications/${applicationId}/interviews`),
  createInterview: (applicationId: number, payload: Omit<InterviewRound, "id" | "application_id" | "outcome" | "created_at" | "updated_at">) =>
    request<InterviewRound>(`/applications/${applicationId}/interviews`, { method: "POST", body: JSON.stringify(payload) }),
  updateInterview: (id: number, payload: Partial<InterviewRound>) =>
    request<InterviewRound>(`/interviews/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteInterview: (id: number) => request<void>(`/interviews/${id}`, { method: "DELETE" }),
  matchApplication: (applicationId: number) => request<MatchResult>(`/applications/${applicationId}/match`),
  undoStatus: (applicationId: number) => request<Application>(`/applications/${applicationId}/undo-status`, { method: "POST" }),
  bulkStatus: (applicationIds: number[], status: ApplicationStatus) => request<Application[]>("/application-actions/bulk-status", { method: "PATCH", body: JSON.stringify({ application_ids: applicationIds, status }) }),
  mergeApplication: (targetId: number, sourceId: number) => request<Application>(`/applications/${targetId}/merge`, { method: "POST", body: JSON.stringify({ source_application_id: sourceId }) }),
  createSampleData: () => request<{ application_id: number }>("/sample-data", { method: "POST" }),
  createCompany: (payload: { name: string; website?: string }) =>
    request<Company>("/companies", { method: "POST", body: JSON.stringify(payload) }),
  createJob: (payload: {
    company_id: number;
    title: string;
    location?: string;
    source?: string;
    source_url?: string;
    jd_text?: string;
  }) => request<Job>("/jobs", { method: "POST", body: JSON.stringify(payload) }),
  updateJob: (id: number, payload: Partial<{
    company_id: number;
    title: string;
    location: string | null;
    source: string | null;
    source_url: string | null;
    jd_text: string | null;
  }>) => request<Job>(`/jobs/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteJob: (id: number) => request<void>(`/jobs/${id}`, { method: "DELETE" }),
  createApplication: (payload: {
    job_id: number;
    resume_version_id?: number;
    notes?: string;
    next_action_at?: string;
  }) => request<Application>("/applications", { method: "POST", body: JSON.stringify(payload) }),
  moveApplication: (id: number, status: ApplicationStatus) =>
    request<Application>(`/applications/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  updateApplication: (id: number, payload: {
    resume_version_id?: number | null;
    notes?: string | null;
    next_action_at?: string | null;
    tags?: string[];
    custom_fields?: Record<string, string>;
  }) => request<Application>(`/applications/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  }),
  deleteApplication: (id: number) =>
    request<void>(`/applications/${id}`, { method: "DELETE" }),
  archiveApplication: (id: number) =>
    request<Application>(`/applications/${id}/archive`, { method: "PATCH" }),
  restoreApplication: (id: number) =>
    request<Application>(`/applications/${id}/restore`, { method: "PATCH" }),
  createResume: (payload: { name: string; file_name?: string; content_text?: string }) =>
    request<ResumeVersion>("/resumes", { method: "POST", body: JSON.stringify(payload) }),
  uploadResume: (name: string, file: File) => {
    const body = new FormData();
    body.append("name", name);
    body.append("file", file);
    return request<ResumeVersion>("/resumes/upload", { method: "POST", body });
  },
  renameResume: (id: number, name: string) =>
    request<ResumeVersion>(`/resumes/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  updateResumeText: (id: number, name: string, contentText: string) =>
    request<ResumeVersion>(`/resumes/${id}`, { method: "PATCH", body: JSON.stringify({ name, content_text: contentText }) }),
  deleteResume: (id: number) => request<void>(`/resumes/${id}`, { method: "DELETE" }),
};
