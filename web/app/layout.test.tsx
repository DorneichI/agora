import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import RootLayout from "./layout";

describe("RootLayout", () => {
  it("renders html/body with font variables and children", () => {
    const html = renderToStaticMarkup(
      <RootLayout params={Promise.resolve({})}>
        <p>child content</p>
      </RootLayout>,
    );

    expect(html).toContain('lang="en"');
    expect(html).toContain("mock-font-sans");
    expect(html).toContain("mock-font-mono");
    expect(html).toContain("child content");
  });
});
