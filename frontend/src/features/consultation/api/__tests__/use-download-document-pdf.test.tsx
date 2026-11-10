import { act, renderHook } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { useDownloadDocumentoPdf } from "../use-download-document-pdf";

const MOCK_ATENDIMENTO_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d";
const MOCK_DOC_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2f";

describe("useDownloadDocumentoPdf Hook (ADR-011 §2.3, US-09)", () => {
  let clickedLinks: HTMLAnchorElement[] = [];

  beforeEach(() => {
    clickedLinks = [];

    window.URL.createObjectURL = vi.fn((_blob: Blob) => {
      return `blob:http://localhost/${Math.random().toString(36).slice(2)}`;
    });

    window.URL.revokeObjectURL = vi.fn((_url: string) => {});

    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clickedLinks.push(this);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("faz o download do PDF criando e revogando blob URL com link DOM temporário", async () => {
    server.use(
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/documents/${MOCK_DOC_ID}/pdf`, () => {
        return new HttpResponse(new Blob(["%PDF-1.4 mock content"], { type: "application/pdf" }), {
          headers: { "Content-Type": "application/pdf" },
        });
      }),
    );

    const { result } = renderHook(() => useDownloadDocumentoPdf(MOCK_ATENDIMENTO_ID));

    expect(result.current.isDownloading).toBe(false);
    expect(result.current.downloadingId).toBeNull();

    let downloadPromise: Promise<void> | undefined;
    act(() => {
      downloadPromise = result.current.downloadPdf(MOCK_DOC_ID, "mock-token");
    });

    await act(async () => {
      await downloadPromise;
    });

    expect(result.current.isDownloading).toBe(false);
    expect(result.current.downloadingId).toBeNull();
    expect(window.URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(window.URL.revokeObjectURL).toHaveBeenCalledTimes(1);
    expect(clickedLinks.length).toBe(1);
    expect(clickedLinks[0].download).toBe(`receita-${MOCK_DOC_ID.substring(0, 8)}.pdf`);
  });

  it("trata erro de rede sem travar estado downloadingId", async () => {
    server.use(
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/documents/${MOCK_DOC_ID}/pdf`, () => {
        return new HttpResponse(null, { status: 500 });
      }),
    );

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result } = renderHook(() => useDownloadDocumentoPdf(MOCK_ATENDIMENTO_ID));

    await act(async () => {
      await result.current.downloadPdf(MOCK_DOC_ID);
    });

    expect(result.current.isDownloading).toBe(false);
    expect(result.current.downloadingId).toBeNull();
    expect(consoleSpy).toHaveBeenCalled();
  });
});
