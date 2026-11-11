import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "研读 · 晨读订阅",
  description: "车辆工程论文晨读的邀请、邮箱验证与偏好管理。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
