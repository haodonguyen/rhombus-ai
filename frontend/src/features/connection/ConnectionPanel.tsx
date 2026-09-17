import { useMutation, useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";

import { describeError, fieldErrors } from "../../api/client";
import { connectToS3, fetchDemoConnection, type S3Connection } from "../../api/s3";
import { FieldError } from "../../components/FieldError";

interface Props {
  connection: S3Connection | null;
  onConnected: (connection: S3Connection) => void;
  onDisconnect: () => void;
}

/**
 * Step one: connect to a bucket with the user's own access key and secret key. The keys
 * are sent once and exchanged for a connection id; they are never stored in the browser.
 */
export function ConnectionPanel({ connection, onConnected, onDisconnect }: Props) {
  const id = useId();
  const [accessKeyId, setAccessKeyId] = useState("");
  const [secretAccessKey, setSecretAccessKey] = useState("");
  const [bucket, setBucket] = useState("");
  const [region, setRegion] = useState("us-east-1");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const demo = useQuery({ queryKey: ["s3-demo"], queryFn: fetchDemoConnection });
  const connect = useMutation({
    mutationFn: connectToS3,
    onSuccess: (created) => {
      setAccessKeyId("");
      setSecretAccessKey("");
      onConnected(created);
    },
  });
  const errors = fieldErrors(connect.error);

  if (connection) {
    return (
      <div className="connected">
        <p>
          Connected to <strong>{connection.bucket}</strong>
          {connection.demo ? " (demo bucket)" : ` in ${connection.region}`}.
        </p>
        <button type="button" className="secondary" onClick={onDisconnect}>
          Use a different bucket
        </button>
      </div>
    );
  }

  return (
    <form
      className="connection-form"
      onSubmit={(event) => {
        event.preventDefault();
        connect.mutate({
          access_key_id: accessKeyId.trim(),
          secret_access_key: secretAccessKey.trim(),
          bucket: bucket.trim(),
          region: region.trim() || "us-east-1",
          endpoint_url: endpointUrl.trim(),
        });
      }}
    >
      <p className="hint">
        Enter the keys for an IAM user that can list and read the bucket. They are held on the
        server, encrypted, for 12 hours and are never written to the database.
      </p>

      <div className="field">
        <label htmlFor={`${id}-key`}>Access key ID</label>
        <input
          id={`${id}-key`}
          value={accessKeyId}
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => setAccessKeyId(event.target.value)}
          aria-invalid={errors.access_key_id ? true : undefined}
        />
        <FieldError id={`${id}-key-error`} messages={errors.access_key_id} />
      </div>

      <div className="field">
        <label htmlFor={`${id}-secret`}>Secret access key</label>
        <input
          id={`${id}-secret`}
          type="password"
          value={secretAccessKey}
          autoComplete="off"
          onChange={(event) => setSecretAccessKey(event.target.value)}
          aria-invalid={errors.secret_access_key ? true : undefined}
        />
        <FieldError id={`${id}-secret-error`} messages={errors.secret_access_key} />
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor={`${id}-bucket`}>Bucket</label>
          <input
            id={`${id}-bucket`}
            value={bucket}
            spellCheck={false}
            onChange={(event) => setBucket(event.target.value)}
            aria-invalid={errors.bucket ? true : undefined}
          />
          <FieldError id={`${id}-bucket-error`} messages={errors.bucket} />
        </div>
        <div className="field">
          <label htmlFor={`${id}-region`}>Region</label>
          <input
            id={`${id}-region`}
            value={region}
            spellCheck={false}
            onChange={(event) => setRegion(event.target.value)}
            aria-invalid={errors.region ? true : undefined}
          />
          <FieldError id={`${id}-region-error`} messages={errors.region} />
        </div>
      </div>

      <button type="button" className="link" onClick={() => setShowAdvanced(!showAdvanced)}>
        {showAdvanced ? "Hide" : "Show"} S3-compatible storage options
      </button>
      {showAdvanced && (
        <div className="field">
          <label htmlFor={`${id}-endpoint`}>Endpoint URL</label>
          <input
            id={`${id}-endpoint`}
            value={endpointUrl}
            placeholder="https://s3.example.com"
            spellCheck={false}
            onChange={(event) => setEndpointUrl(event.target.value)}
            aria-invalid={errors.endpoint_url ? true : undefined}
          />
          <FieldError id={`${id}-endpoint-error`} messages={errors.endpoint_url} />
          <p className="hint">Leave blank for Amazon S3. Set it for MinIO or similar storage.</p>
        </div>
      )}

      {connect.isError && Object.keys(errors).length === 0 && (
        <p role="alert" className="error">
          {describeError(connect.error)}
        </p>
      )}

      <div className="actions">
        <button type="submit" disabled={connect.isPending}>
          {connect.isPending ? "Connecting…" : "Connect"}
        </button>
        {demo.data?.available && demo.data.connection_id && (
          <button
            type="button"
            className="secondary"
            onClick={() =>
              onConnected({
                connection_id: demo.data.connection_id as string,
                bucket: demo.data.bucket ?? "",
                region: demo.data.region ?? "",
                demo: true,
                expires_in: 0,
              })
            }
          >
            Or try the demo bucket
          </button>
        )}
      </div>
    </form>
  );
}
