import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TierBadge } from "./TierBadge";

describe("TierBadge", () => {
  it("renders the tier label with underscores replaced by spaces", () => {
    render(<TierBadge tier="high_risk" />);
    expect(screen.getByText("high risk")).toBeInTheDocument();
  });

  it("renders an unrecognized tier without crashing", () => {
    render(<TierBadge tier="unknown_tier" />);
    expect(screen.getByText("unknown tier")).toBeInTheDocument();
  });
});
