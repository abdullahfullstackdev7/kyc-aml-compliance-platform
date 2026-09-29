import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/lib/auth";
import Login from "./Login";

function renderLogin() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Login />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("Login", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("moves to the MFA step when the API reports mfa_required", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "mfa_required", user_id: 42 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderLogin();
    await userEvent.type(screen.getByLabelText(/email/i), "reviewer@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "correct-password");
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => {
      expect(screen.getByText(/enter your mfa code/i)).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/login"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows the server error message when login fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid credentials" }), { status: 401 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderLogin();
    await userEvent.type(screen.getByLabelText(/email/i), "reviewer@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "wrong-password");
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => {
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
    });
  });

  it("goes back from the MFA step to the credentials step", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "mfa_required", user_id: 42 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderLogin();
    await userEvent.type(screen.getByLabelText(/email/i), "reviewer@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "correct-password");
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => screen.getByText(/enter your mfa code/i));

    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });
});
