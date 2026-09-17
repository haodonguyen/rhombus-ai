import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { S3Connection } from "../../api/s3";
import { jsonResponse, mockFetch, renderWithClient } from "../../test/utils";
import { ConnectionPanel } from "./ConnectionPanel";

const CONNECTED: S3Connection = {
  connection_id: "conn-1",
  bucket: "customer-bucket",
  region: "ap-southeast-2",
  demo: false,
  expires_in: 43200,
};

function demoUnavailable() {
  return mockFetch((url) =>
    url.pathname.endsWith("/demo/")
      ? jsonResponse({ available: false })
      : jsonResponse(CONNECTED, 201),
  );
}

function requestBody(fetchMock: ReturnType<typeof mockFetch>) {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
  return JSON.parse(String(call?.[1]?.body));
}

describe("ConnectionPanel", () => {
  it("exchanges the entered keys for a connection", async () => {
    const fetchMock = demoUnavailable();
    const onConnected = vi.fn();

    renderWithClient(
      <ConnectionPanel connection={null} onConnected={onConnected} onDisconnect={vi.fn()} />,
    );
    await userEvent.type(screen.getByLabelText("Access key ID"), "AKIAEXAMPLE");
    await userEvent.type(screen.getByLabelText("Secret access key"), "secret-value");
    await userEvent.type(screen.getByLabelText("Bucket"), "customer-bucket");
    await userEvent.clear(screen.getByLabelText("Region"));
    await userEvent.type(screen.getByLabelText("Region"), "ap-southeast-2");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() => expect(onConnected).toHaveBeenCalledWith(CONNECTED));
    expect(requestBody(fetchMock)).toEqual({
      access_key_id: "AKIAEXAMPLE",
      secret_access_key: "secret-value",
      bucket: "customer-bucket",
      region: "ap-southeast-2",
      endpoint_url: "",
    });
  });

  it("keeps the secret out of the rendered page", async () => {
    demoUnavailable();

    renderWithClient(
      <ConnectionPanel connection={null} onConnected={vi.fn()} onDisconnect={vi.fn()} />,
    );
    await userEvent.type(screen.getByLabelText("Secret access key"), "secret-value");

    expect(screen.getByLabelText("Secret access key")).toHaveAttribute("type", "password");
    expect(document.body.textContent).not.toContain("secret-value");
  });

  it("shows per-field errors from the server", async () => {
    mockFetch((url) =>
      url.pathname.endsWith("/demo/")
        ? jsonResponse({ available: false })
        : jsonResponse(
            {
              error: {
                code: "VALIDATION_ERROR",
                message: "Invalid input.",
                details: { bucket: ["This field may not be blank."] },
              },
            },
            400,
          ),
    );

    renderWithClient(
      <ConnectionPanel connection={null} onConnected={vi.fn()} onDisconnect={vi.fn()} />,
    );
    await userEvent.type(screen.getByLabelText("Access key ID"), "AKIAEXAMPLE");
    await userEvent.type(screen.getByLabelText("Secret access key"), "secret-value");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByText("This field may not be blank.")).toBeInTheDocument();
  });

  it("reports rejected credentials", async () => {
    mockFetch((url) =>
      url.pathname.endsWith("/demo/")
        ? jsonResponse({ available: false })
        : jsonResponse(
            {
              error: {
                code: "S3_CREDENTIALS_INVALID",
                message: "S3 rejected these credentials.",
              },
            },
            400,
          ),
    );

    renderWithClient(
      <ConnectionPanel connection={null} onConnected={vi.fn()} onDisconnect={vi.fn()} />,
    );
    await userEvent.type(screen.getByLabelText("Access key ID"), "AKIAEXAMPLE");
    await userEvent.type(screen.getByLabelText("Secret access key"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("S3 rejected these credentials.");
  });

  it("offers the demo bucket when the deployment has one", async () => {
    mockFetch(() =>
      jsonResponse({ available: true, connection_id: "demo", bucket: "datasets", demo: true }),
    );
    const onConnected = vi.fn();

    renderWithClient(
      <ConnectionPanel connection={null} onConnected={onConnected} onDisconnect={vi.fn()} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: /demo bucket/ }));

    expect(onConnected).toHaveBeenCalledWith(expect.objectContaining({ connection_id: "demo" }));
  });

  it("shows the connected bucket and allows switching", async () => {
    demoUnavailable();
    const onDisconnect = vi.fn();

    renderWithClient(
      <ConnectionPanel connection={CONNECTED} onConnected={vi.fn()} onDisconnect={onDisconnect} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Use a different bucket" }));

    expect(screen.getByText("customer-bucket")).toBeInTheDocument();
    expect(onDisconnect).toHaveBeenCalled();
  });
});
