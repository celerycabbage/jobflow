import { ApiError, ApplicationStatus } from "./api";

export const columns: { key: ApplicationStatus; label: string; hint: string }[] = [
  { key: "saved", label: "待投递", hint: "准备材料" },
  { key: "applied", label: "已投递", hint: "等待反馈" },
  { key: "assessment", label: "笔试", hint: "进行中" },
  { key: "interview", label: "面试", hint: "准备沟通" },
  { key: "offer", label: "Offer", hint: "等待决策" },
  { key: "closed", label: "已结束", hint: "归档" },
];

export function friendlyError(error: unknown) {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return "无法连接后端，请确认 API 已启动";
  return "操作失败，请稍后再试";
}
