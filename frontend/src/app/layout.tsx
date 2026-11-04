import type {Metadata} from "next";
import type {ReactNode} from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "SharpBuild AI Website Assistant (demo)",
  description:
    "A retrieval-augmented chatbot that answers questions using the public content of sharpbuild.io.",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang='en'>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
