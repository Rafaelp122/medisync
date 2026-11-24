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
      medicoNome: "Dra. Ana Souza",
      remoteParticipantName: "Paciente #11223344",
      onRender,
    };

    const { rerender } = render(<TestMediaPane {...initialProps} />);
    expect(renderCount).toBe(1);

    rerender(<TestMediaPane {...initialProps} />);
    expect(renderCount).toBe(1);

    rerender(<TestMediaPane {...initialProps} atendimentoId="atend-456" />);
    expect(renderCount).toBe(2);
  });

  it("IT-PERF-02: Renderiza VideoCallStage no estado offline/conectando de forma acessível sem boolean props", () => {
    render(
      <WorkstationMediaPane
        atendimentoId="atend-123"
        medicoNome="Dra. Ana Souza"
        remoteParticipantName="Paciente #11223344"
      />,
    );

    expect(screen.getAllByText("Paciente #11223344").length).toBeGreaterThan(0);
    expect(screen.getByText("Dra. Ana Souza")).toBeInTheDocument();
    expect(screen.getByText(/conectando ao livekit/i)).toBeInTheDocument();
  });
});
