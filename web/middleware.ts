import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// `:path*` (rather than `(.*)`) maps to how Next.js actually matches path segments, so it
// requires a `/` boundary after "dashboard" -- `/dashboard(.*)` would also match unrelated
// sibling routes like `/dashboard-preview` since nothing forces a separator before the
// wildcard. This is Clerk's own documented recommendation.
const isProtectedRoute = createRouteMatcher(["/dashboard/:path*"]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtectedRoute(req)) {
    await auth.protect();
  }
});

export const config = {
  // Run on every request except Next.js's own internal static/image-optimization assets.
  // The previous matcher additionally excluded anything ending in a hardcoded list of file
  // extensions (html/css/js/csv/docx/etc.), which meant Clerk's middleware -- and therefore
  // `auth.protect()` -- would never even run for a *protected* route whose path happened to
  // end in one of those extensions (e.g. a future `/dashboard/report.csv` export route),
  // serving it to unauthenticated requests.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)", "/(api|trpc)(.*)"],
};
