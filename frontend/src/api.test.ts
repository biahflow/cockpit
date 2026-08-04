import { afterEach, expect, test, vi } from "vitest";

import { acceptInvitation, createInvitation, documentDownloadUrl, getConfig, listInvitations, listNotifications, listUsers, login, markAllNotificationsRead, markNotificationRead } from "./api";

afterEach(() => vi.unstubAllGlobals());

test("envia o token CSRF ao autenticar", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: "token-seguro" }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: 1, username: "admin" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  await login("admin", "admin");

  expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/v1/auth/csrf/", { credentials: "include" });
  expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/v1/auth/login/", expect.objectContaining({
    method: "POST",
    credentials: "include",
    headers: expect.objectContaining({ "Content-Type": "application/json", "X-CSRFToken": "token-seguro" }),
  }));
});

test("lista convites e usuários via GET", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 1 }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 2 }]), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  expect(await listInvitations()).toEqual([{ id: 1 }]);
  expect(await listUsers()).toEqual([{ id: 2 }]);
  expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/v1/invitations/", expect.objectContaining({ credentials: "include" }));
  expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/v1/users/", expect.objectContaining({ credentials: "include" }));
});

test("cria convite e aceita convite via POST com CSRF", async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 })));
  vi.stubGlobal("fetch", fetchMock);

  await createInvitation("pessoa@x.com", "delivery");
  await acceptInvitation({ token: "abc", username: "novo", password: "SenhaSegura123!" });

  expect(fetchMock).toHaveBeenCalledWith("/api/v1/invitations/", expect.objectContaining({ method: "POST" }));
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/invitations/accept/", expect.objectContaining({ method: "POST" }));
});

test("monta a URL de download do documento", () => {
  expect(documentDownloadUrl(7)).toBe("/api/v1/documents/7/download/");
});

test("busca config e notificações via GET", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ ai_enabled: true, calendar_enabled: false, esign_enabled: false }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 1 }]), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  expect((await getConfig()).ai_enabled).toBe(true);
  expect(await listNotifications()).toEqual([{ id: 1 }]);
});

test("marca notificações como lidas via POST", async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 })));
  vi.stubGlobal("fetch", fetchMock);

  await markNotificationRead(1);
  await markAllNotificationsRead();

  expect(fetchMock).toHaveBeenCalledWith("/api/v1/notifications/1/read/", expect.objectContaining({ method: "POST" }));
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/notifications/read-all/", expect.objectContaining({ method: "POST" }));
});
