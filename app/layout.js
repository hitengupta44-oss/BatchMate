import { Caveat, Newsreader, Public_Sans } from "next/font/google";
import { SessionProvider } from "../lib/session";
import "./globals.css";

const sans = Public_Sans({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const serif = Newsreader({ subsets: ["latin"], variable: "--font-serif", display: "swap" });
const hand = Caveat({ subsets: ["latin"], weight: ["500", "700"], variable: "--font-hand", display: "swap" });

export const metadata = {
  title: "Batchmate",
  description: "Mock interviews that remember you, and what your seniors were asked.",
  icons: {
    icon:
      "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%231D3B8B'/%3E%3Cpath d='M9 4v24' stroke='%23C8233A' stroke-width='2'/%3E%3Cpath d='M13 11h12M13 16h12M13 21h8' stroke='white' stroke-width='2'/%3E%3C/svg%3E",
  },
};

export const viewport = { width: "device-width", initialScale: 1, themeColor: "#1D3B8B" };

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable} ${hand.variable}`}>
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
