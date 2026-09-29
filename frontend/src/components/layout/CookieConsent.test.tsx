import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CookieConsent } from "./CookieConsent";

const STORAGE_KEY = "sentinelkyc-cookie-consent";

function renderBanner() {
  return render(
    <MemoryRouter>
      <CookieConsent />
    </MemoryRouter>,
  );
}

describe("CookieConsent", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows the banner when no choice has been recorded", () => {
    renderBanner();
    expect(screen.getByText(/we use cookies/i)).toBeInTheDocument();
  });

  it("does not show the banner if a choice was already recorded", () => {
    localStorage.setItem(STORAGE_KEY, "accepted");
    renderBanner();
    expect(screen.queryByText(/we use cookies/i)).not.toBeInTheDocument();
  });

  it("hides the banner and persists the choice on Accept", () => {
    renderBanner();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(screen.queryByText(/we use cookies/i)).not.toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).toBe("accepted");
  });

  it("hides the banner and persists the choice on Reject", () => {
    renderBanner();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(localStorage.getItem(STORAGE_KEY)).toBe("rejected");
  });
});
