import { BackendStatus } from "./components/BackendStatus";

export function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>NL Regex Platform</h1>
        <BackendStatus />
      </header>
      <main>
        <p>Select a file from S3, describe a pattern, and transform your data at scale.</p>
      </main>
    </div>
  );
}
