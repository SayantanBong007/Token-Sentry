import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Token-Sentry Analytics Dashboard",
  description: "Real-time performance and cost analytics for the Token-Sentry API Gateway.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
