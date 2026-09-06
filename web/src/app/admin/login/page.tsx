import type { Metadata } from "next";

export const metadata: Metadata = { title: "后台登录" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string; next?: string }> }) {
  const query = await searchParams;
  return <main className="inner-page admin-page"><header className="page-hero"><p className="eyebrow">SECURE ACCESS</p><h1>运营后台登录</h1><p>登录后才能查看内部候选资料。生产环境请接入企业身份提供方。</p></header><form className="admin-form" method="post" action="/api/admin/session"><input type="hidden" name="next" value={query.next?.startsWith("/admin") ? query.next : "/admin"}/><label>账号<input name="username" autoComplete="username" required/></label><label>密码<input name="password" type="password" autoComplete="current-password" required/></label><div className="form-actions"><button type="submit">安全登录</button>{query.error && <span className="action-error" role="alert">账号或密码错误</span>}</div></form></main>;
}
