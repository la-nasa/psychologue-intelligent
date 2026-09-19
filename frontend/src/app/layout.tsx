import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Mensana",
    template: "%s · Mensana",
  },
  description: "Un espace pour parler, en toute confiance.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F8F6F2" },
    { media: "(prefers-color-scheme: dark)", color: "#12171C" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        {/* Applique le thème choisi avant le premier rendu React pour éviter
            un flash de mauvais thème (FOUC) — lu depuis localStorage, retombe
            sur la préférence système si rien n'a jamais été choisi. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('mensana-theme');if(t==='dark'||t==='light'){document.documentElement.classList.add(t);}var a=JSON.parse(localStorage.getItem('mensana-a11y')||'{}');if(a.highContrast)document.documentElement.classList.add('high-contrast');if(a.largeText)document.documentElement.classList.add('large-text');if(a.reducedMotion)document.documentElement.classList.add('reduce-motion');}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
