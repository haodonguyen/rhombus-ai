import { skipToken, useQuery } from "@tanstack/react-query";

import { fetchJob } from "../../api/jobs";
import { isTerminal, pollInterval } from "./polling";

export function jobQueryKey(jobId: string | null) {
  return ["job", jobId] as const;
}

/** Fetch a job and keep polling (with backoff) until it reaches a terminal status. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: jobQueryKey(jobId),
    queryFn: jobId ? () => fetchJob(jobId) : skipToken,
    refetchInterval: (query) => {
      const job = query.state.data;
      return job && isTerminal(job.status) ? false : pollInterval(query.state.dataUpdateCount);
    },
  });
}
