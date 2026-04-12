import type { Metadata } from "next";
import "./globals.css";

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
        {children}
      </body>
    </html>
  );
}
