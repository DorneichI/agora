import "@testing-library/jest-dom/vitest";

import { createElement, type ReactNode } from "react";
import { vi } from "vitest";

// Mock Clerk components to avoid requiring a real Clerk backend or API key just to render
// client-side UI components in tests. These are thin UI wrappers with no internal logic;
// tests verify behavior, not Clerk's implementation.
vi.mock("@clerk/nextjs", () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  UserButton: () =>
    createElement("div", { "data-testid": "clerk-user-button" }),
  SignIn: () => createElement("div", { "data-testid": "clerk-sign-in" }),
  SignUp: () => createElement("div", { "data-testid": "clerk-sign-up" }),
}));

// Only mock `clerkMiddleware` (which orchestrates auth checks), keeping everything else real
// (e.g., `createRouteMatcher`, `currentUser()`, `auth()`). Functions like `createRouteMatcher`
// need no backend/network dependency, so testing the real implementation is strictly better than
// mocking it. Tests that need auth context must provide it explicitly, not assume Clerk is mocked.
vi.mock("@clerk/nextjs/server", async () => {
  const actual = await vi.importActual<typeof import("@clerk/nextjs/server")>(
    "@clerk/nextjs/server",
  );
  return {
    ...actual,
    clerkMiddleware: (handler: unknown) => handler,
  };
});

// Mock next/font/google because it fetches font files over the network at import time. Unlike
// Next.js's own test setup (next/jest), this project uses Vitest, which doesn't automatically
// mock fonts. Mocking prevents network calls and build delays during test runs.
vi.mock("next/font/google", () => ({
  Geist: () => ({ variable: "mock-font-sans" }),
  Geist_Mono: () => ({ variable: "mock-font-mono" }),
}));
