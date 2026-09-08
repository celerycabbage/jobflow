import { ArrowRight } from "lucide-react";
import { FormEvent, useState } from "react";

import { authenticate } from "../api";
import { friendlyError } from "../ui";

export function AuthScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await authenticate(mode, email, password);
      onAuthenticated();
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return <main className="auth-shell">
    <section className="auth-story">
      <div className="brand brand--light"><span className="brand-mark"><ArrowRight size={18} /></span><span>JobFlow</span></div>
      <div className="story-copy"><p className="eyebrow">让每一次投递都有迹可循</p><h1>把求职从焦虑，<br />变成清晰的下一步。</h1><p>集中管理岗位、简历版本和面试进度，用真实数据复盘自己的求职过程。</p></div>
      <div className="story-proof"><div><strong>6</strong><span>阶段清晰流转</span></div><div><strong>1</strong><span>处管理所有机会</span></div></div>
    </section>
    <section className="auth-panel">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-heading"><span className="mobile-brand">JobFlow</span><h2>{mode === "login" ? "欢迎回来" : "创建你的工作区"}</h2><p>{mode === "login" ? "继续推进你的求职计划" : "从第一条真实投递开始"}</p></div>
        <label><span>邮箱</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required /></label>
        <label><span>密码</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少 8 位" minLength={8} required /></label>
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button auth-submit" disabled={submitting}>{submitting ? "正在处理…" : mode === "login" ? "登录" : "创建账户"}{!submitting && <ArrowRight size={17} />}</button>
        <p className="auth-switch">{mode === "login" ? "第一次使用？" : "已经有账户？"}<button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>{mode === "login" ? "免费创建" : "返回登录"}</button></p>
      </form>
    </section>
  </main>;
}
