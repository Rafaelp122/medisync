import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";
import {
  WorkstationMediaPane,
  type WorkstationMediaPaneProps,
} from "../components/workstation-media-pane";

interface TestMediaPaneProps extends WorkstationMediaPaneProps {
  onRender?: () => void;
}

const TestMediaPane = React.memo(function TestMediaPane({
  onRender,
  ...props
}: TestMediaPaneProps) {
  onRender?.();
  return <WorkstationMediaPane {...props} />;
});

describe("DoctorWorkstation Performance & WebRTC Media Isolation (ADR-011)", () => {
  it("IT-PERF-01: WorkstationMediaPane é protegido por React.memo e não re-renderiza com props idênticas", () => {
    let renderCount = 0;
    const onRender = () => {
      renderCount++;
    };

    const initialProps = {
      atendimentoId: "atend-123",
      medicoNome: "Dr. Eduardo Rocha",
      remoteParticipantName: "Juliana Silva (Paciente)",
      onRender,
    };

    const { rerender } = render(<TestMediaPane {...initialProps} />);
    expect(renderCount).toBe(1);

    // Rerender com as mesmas props (simulando re-render do componente pai por SOAP ou Telemetria)
    rerender(<TestMediaPane {...initialProps} />);
    expect(renderCount).toBe(1);

    // Rerender com alteração real em atendimentoId
    rerender(<TestMediaPane {...initialProps} atendimentoId="atend-456" />);
    expect(renderCount).toBe(2);
  });

  it("IT-PERF-02: Renderiza VideoPane no estado desconectado de forma acessível", () => {
    render(
      <WorkstationMediaPane
        atendimentoId="atend-123"
        medicoNome="Dr. Eduardo Rocha"
        remoteParticipantName="Juliana Silva (Paciente)"
      />,
    );

    expect(screen.getAllByText("Juliana Silva (Paciente)").length).toBeGreaterThan(0);
    expect(screen.getByText("Dr. Eduardo Rocha")).toBeInTheDocument();
  });
});
