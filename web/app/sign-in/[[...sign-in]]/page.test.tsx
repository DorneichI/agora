import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Page from "./page";

describe("Sign-in page", () => {
  it("renders the sign-in component", () => {
    render(<Page />);

    expect(screen.getByTestId("clerk-sign-in")).toBeInTheDocument();
  });
});
