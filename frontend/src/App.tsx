import { useState } from "react";

import { BackendStatus } from "./components/BackendStatus";
import { ColumnPicker } from "./features/files/ColumnPicker";
import { FileList } from "./features/files/FileList";
import { JobForm } from "./features/jobs/JobForm";
import { JobStatus } from "./features/jobs/JobStatus";
import { useJob } from "./features/jobs/useJob";
import { ResultsTable } from "./features/results/ResultsTable";

export function App() {
  const [sourceKey, setSourceKey] = useState<string | null>(null);
  const [targetColumns, setTargetColumns] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);

  function selectFile(key: string) {
    setSourceKey(key);
    setTargetColumns([]);
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>NL Regex Platform</h1>
        <BackendStatus />
      </header>

      <main className="workflow">
        <section className="panel" aria-labelledby="step-file">
          <h2 id="step-file">1. Choose a file</h2>
          <FileList selectedKey={sourceKey} onSelect={selectFile} />
        </section>

        {sourceKey && (
          <section className="panel" aria-labelledby="step-configure">
            <h2 id="step-configure">2. Configure the replacement</h2>
            <ColumnPicker
              key={sourceKey}
              fileKey={sourceKey}
              selected={targetColumns}
              onChange={setTargetColumns}
            />
            <JobForm
              sourceKey={sourceKey}
              targetColumns={targetColumns}
              onSubmitted={(created) => setJobId(created.id)}
            />
          </section>
        )}

        {jobId && (
          <section className="panel" aria-labelledby="step-job">
            <h2 id="step-job">3. Job</h2>
            <JobStatus jobId={jobId} />
            {job.data?.status === "SUCCESS" && <ResultsTable key={jobId} jobId={jobId} />}
          </section>
        )}
      </main>
    </div>
  );
}
