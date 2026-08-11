import type { Metadata } from "next";
import "./globals.css";
import I18nRuntime from "@/components/i18n-runtime";

export const metadata: Metadata = {
  title: "SAVIA — Superviseur Intelligent Clinique",
  description: "Plateforme de maintenance prédictive pour équipements de radiologie médicale",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr" className="dark">
      <body className="antialiased min-h-screen bg-savia-bg text-savia-text">
        <I18nRuntime />
        {children}
      </body>
    </html>
  );
}
