import Link from "next/link";

export default function NotFound() {
  return (
    <main className="wrap">
      <p className="eyebrow">404 · Out of bounds</p>
      <h1 className="disp text-4xl">This page isn&apos;t on the court.</h1>
      <p className="mt-4 max-w-xl">
        The page you were looking for doesn&apos;t exist. Head back to the lobby.
      </p>
      <div className="row">
        <Link href="/" className="btn btn-accent">
          Back to the start
        </Link>
      </div>
    </main>
  );
}
