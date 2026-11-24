import { render } from "@testing-library/react";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";
import { Form, FormLabel } from "./form";

function InvalidFormUsageProbe() {
  const methods = useForm({ defaultValues: { campo: "" } });
  return (
    <Form {...methods}>
      <FormLabel>Campo fora de FormField</FormLabel>
    </Form>
  );
}

describe("ui/form (guarda if (!fieldContext))", () => {
  it("lança erro explícito de FormField ausente antes de ler fieldContext.name", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      expect(() => render(<InvalidFormUsageProbe />)).toThrow(
        "useFormField should be used within <FormField>",
      );
    } finally {
      errorSpy.mockRestore();
    }
  });
});
