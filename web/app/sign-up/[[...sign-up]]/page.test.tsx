import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Page from "./page";

describe("Sign-up page", () => {
  it("renders the sign-up component", () => {
    render(<Page />);

    expect(screen.getByTestId("clerk-sign-up")).toBeInTheDocument();
  });
});
