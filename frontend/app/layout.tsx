import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TraceQ — the forensic layer for the internet",
  description: "Reconstruct a file's verifiable history. No guesses — only what can be proven.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-paper text-[#e6e9f0] antialiased">{children}</body>
    </html>
  );
}
