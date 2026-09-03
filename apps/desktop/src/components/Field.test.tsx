// SPDX-License-Identifier: AGPL-3.0-or-later

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Chips } from "./Chips";
import { Field } from "./Field";
import { FormSection } from "./FormSection";

describe("Field", () => {
  it("links label, control, and hint", () => {
    render(
      <Field id="model" label="Model" hint="Example: gpt-4o-mini">
        <input id="model" />
      </Field>,
    );
    expect(screen.getByLabelText("Model")).toBeInTheDocument();
    expect(screen.getByText("Example: gpt-4o-mini")).toHaveClass("field__hint");
  });

  it("announces errors as alerts", () => {
    render(
      <Field id="key" label="API key" error="Paste an API key.">
        <input id="key" />
      </Field>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Paste an API key.");
    expect(screen.getByRole("alert")).toHaveClass("field__error");
  });

  it("renders no hint or error paragraph when neither is given", () => {
    const { container } = render(
      <Field id="plain" label="Plain">
        <input id="plain" />
      </Field>,
    );
    expect(container.querySelector(".field__hint")).toBeNull();
    expect(container.querySelector(".field__error")).toBeNull();
  });
});

describe("FormSection", () => {
  it("renders the title, lead, actions, and children", () => {
    render(
      <FormSection title="Chat model" lead="Pick the model Kronos chats with." actions={<button type="button">Save</button>}>
        <p>Body</p>
      </FormSection>,
    );
    expect(screen.getByRole("heading", { level: 3, name: "Chat model" })).toHaveClass("form-section__title");
    expect(screen.getByText("Pick the model Kronos chats with.")).toHaveClass("form-section__lead");
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
  });
});

describe("Chips", () => {
  const options = [
    { id: "openai", label: "OpenAI" },
    { id: "ollama", label: "Ollama" },
  ] as const;

  it("renders a radio group with the active chip checked", () => {
    render(<Chips label="Provider" value="openai" options={options} onChange={vi.fn()} />);
    expect(screen.getByRole("radiogroup", { name: "Provider" })).toHaveClass("chips");
    expect(screen.getByRole("radio", { name: "OpenAI" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "OpenAI" })).toHaveClass("chip", "chip--active");
    expect(screen.getByRole("radio", { name: "Ollama" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("radio", { name: "Ollama" })).not.toHaveClass("chip--active");
  });

  it("reports the clicked option", async () => {
    const onChange = vi.fn();
    render(<Chips label="Provider" value="openai" options={options} onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "Ollama" }));
    expect(onChange).toHaveBeenCalledWith("ollama");
  });
});
