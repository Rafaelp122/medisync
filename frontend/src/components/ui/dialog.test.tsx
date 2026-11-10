import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./dialog";

describe("Dialog Primitive & Safe Area Mobile Ergonomics", () => {
  it("IT-DIALOG-01: DialogContent aplica compensação de Safe Area Inset no mobile", () => {
    render(
      <Dialog open={true}>
        <DialogContent>
          <DialogTitle>Título do Diálogo</DialogTitle>
          <DialogDescription>Descrição do Diálogo</DialogDescription>
        </DialogContent>
      </Dialog>,
    );

    const dialogContent = screen.getByRole("dialog");
    expect(dialogContent.className).toMatch(/safe-area-inset-bottom/);
    expect(dialogContent.className).toMatch(/overscroll-contain/);
  });
});
