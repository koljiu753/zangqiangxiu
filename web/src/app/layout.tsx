import type { Metadata } from "next";
import { SiteHeader } from "@/components/site-header";
import "./globals.css";

export const metadata: Metadata = { title: { default: "智绣乡村", template: "%s | 智绣乡村" }, description: "藏羌纹样数字化保护与创新设计平台" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body><SiteHeader />{children}<footer><strong>智绣乡村 · 阿热灵绣</strong><span>以技术保存纹样，以设计连接当代生活</span></footer></body></html>;
}
