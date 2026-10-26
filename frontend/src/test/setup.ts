import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { server } from "@/mocks/server";

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
});

afterEach(() => {
  server.resetHandlers();
  vi.useRealTimers();
});

afterAll(() => {
  server.close();
});
