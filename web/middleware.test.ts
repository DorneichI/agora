import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

import middlewareExport from "./middleware";

type AuthStub = { protect: () => void };
type MiddlewareHandler = (auth: AuthStub, req: NextRequest) => Promise<void>;

const middleware = middlewareExport as unknown as MiddlewareHandler;

function makeAuthStub(): AuthStub {
  return { protect: vi.fn() };
}

describe("middleware", () => {
  it("protects /dashboard routes", async () => {
    const auth = makeAuthStub();
    const req = new NextRequest("https://example.com/dashboard/foo");

    await middleware(auth, req);

    expect(auth.protect).toHaveBeenCalledTimes(1);
  });

  it("does not protect other routes", async () => {
    const auth = makeAuthStub();
    const req = new NextRequest("https://example.com/");

    await middleware(auth, req);

    expect(auth.protect).not.toHaveBeenCalled();
  });
});
