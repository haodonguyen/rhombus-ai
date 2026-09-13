import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "../api/health";

export function BackendStatus() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    retry: false,
  });

  if (isPending) {
    return (
      <span className="status" role="status">
        Backend: checking…
      </span>
    );
  }
  if (isError) {
    return (
      <span className="status" role="status" data-state="unreachable">
        Backend: unreachable
      </span>
    );
  }
  return (
    <span className="status" role="status" data-state={data.status}>
      Backend: {data.status}
    </span>
  );
}
