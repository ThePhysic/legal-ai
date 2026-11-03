import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "legal.ai — understand the source",
  description:
    "Source-linked California legal research and private document review. Local, offline, and clear about what the evidence supports.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
