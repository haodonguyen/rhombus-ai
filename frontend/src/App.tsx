import { useState } from "react";

import type { S3Connection } from "./api/s3";
import { BackendStatus } from "./components/BackendStatus";
import { ConnectionPanel } from "./features/connection/ConnectionPanel";
import { ColumnPicker } from "./features/files/ColumnPicker";
import { FileList } from "./features/files/FileList";
import { JobForm } from "./features/jobs/JobForm";
import { JobStatus } from "./features/jobs/JobStatus";
import { useJob } from "./features/jobs/useJob";
import { ResultsTable } from "./features/results/ResultsTable";

export function App() {
  const [connection, setConnection] = useState<S3Connection | null>(null);
  const [sourceKey, setSourceKey] = useState<string | null>(null);
  const [targetColumns, setTargetColumns] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);

  function selectFile(key: string) {
    setSourceKey(key);
    setTargetColumns([]);
  }

  function disconnect() {
    setConnection(null);
    setSourceKey(null);
    setTargetColumns([]);
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>NL Regex Platform</h1>
        <BackendStatus />
      </header>

      <main className="workflow">
        <section className="panel" aria-labelledby="step-connect">
          <h2 id="step-connect">1. Connect to S3</h2>
          <ConnectionPanel
            connection={connection}
            onConnected={setConnection}
            onDisconnect={disconnect}
          />
        </section>

        {connection && (
          <section className="panel" aria-labelledby="step-file">
            <h2 id="step-file">2. Choose a file</h2>
            <FileList
              key={connection.connection_id}
              connectionId={connection.connection_id}
              selectedKey={sourceKey}
              onSelect={selectFile}
            />
          </section>
        )}

        {connection && sourceKey && (
          <section className="panel" aria-labelledby="step-configure">
            <h2 id="step-configure">3. Configure the replacement</h2>
            <ColumnPicker
              key={sourceKey}
              connectionId={connection.connection_id}
              fileKey={sourceKey}
              selected={targetColumns}
              onChange={setTargetColumns}
            />
            <JobForm
              connectionId={connection.connection_id}
              sourceKey={sourceKey}
              targetColumns={targetColumns}
              onSubmitted={(created) => setJobId(created.id)}
            />
          </section>
        )}

        {jobId && (
          <section className="panel" aria-labelledby="step-job">
            <h2 id="step-job">4. Job</h2>
            <JobStatus jobId={jobId} />
            {job.data?.status === "SUCCESS" && <ResultsTable key={jobId} jobId={jobId} />}
          </section>
        )}
      </main>
    </div>
  );
}
