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
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased min-h-screen bg-savia-bg text-savia-text">
        <I18nRuntime />
        {children}
      </body>
    </html>
  );
}
