"use client";
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) { return <main className="state-page"><h1>暂时无法载入内容</h1><p>API 未响应或演示回退已关闭，请检查环境配置。</p><button className="primary-button" onClick={reset}>重新加载</button></main>; }
