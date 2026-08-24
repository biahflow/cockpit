import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { DesignSystemPage } from "./DesignSystemPage";

const mocks = vi.hoisted(() => ({ user: { is_admin: true, role: "admin" } as { is_admin: boolean; role: string } }));
vi.mock("../auth", () => ({ useAuth: () => ({ user: mocks.user }) }));

beforeEach(() => { mocks.user = { is_admin: true, role: "admin" }; });
afterEach(cleanup);

test("admin vê o título", () => {
  render(<DesignSystemPage />);
  expect(screen.getByRole("heading", { name: "Design system" })).toBeInTheDocument();
});

test("não-admin vê sem permissão", () => {
  mocks.user = { is_admin: false, role: "sales" };
  render(<DesignSystemPage />);
  expect(screen.getByText("Sem permissão para ver o design system.")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Design system" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
