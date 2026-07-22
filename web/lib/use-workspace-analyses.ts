"use client";

import { useQueries } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { getAnalysis, getAnalytics } from "@/lib/api/analyses";
import { normalizeApiError } from "@/lib/api/client";
import { getRecentAnalysisIds, RECENT_ANALYSES_UPDATED_EVENT } from "@/lib/recent-analyses";
import {
  deriveWorkspaceSummary,
  type WorkspaceAnalysisRecord,
} from "@/lib/workspace-data";

export function useWorkspaceAnalyses() {
  const [analysisIds, setAnalysisIds] = useState<string[]>([]);

  useEffect(() => {
    const loadIds = () => setAnalysisIds(getRecentAnalysisIds());
    loadIds();
    window.addEventListener(RECENT_ANALYSES_UPDATED_EVENT, loadIds);
    window.addEventListener("storage", loadIds);
    return () => {
      window.removeEventListener(RECENT_ANALYSES_UPDATED_EVENT, loadIds);
      window.removeEventListener("storage", loadIds);
    };
  }, []);

  const jobQueries = useQueries({
    queries: analysisIds.map((analysisId) => ({
      queryKey: ["analysis", analysisId],
      queryFn: () => getAnalysis(analysisId),
    })),
  });

  const analyticsIds = analysisIds.filter((_, index) => {
    const job = jobQueries[index]?.data;
    return job?.analytics_completed === true && job.status !== "failed";
  });

  const analyticsQueries = useQueries({
    queries: analyticsIds.map((analysisId) => ({
      queryKey: ["analysis", analysisId, "analytics"],
      queryFn: () => getAnalytics(analysisId),
      retry: false,
    })),
  });

  const records = useMemo<WorkspaceAnalysisRecord[]>(() => {
    const analyticsById = new Map(
      analyticsIds.map((analysisId, index) => [analysisId, analyticsQueries[index]]),
    );
    return analysisIds.map((analysisId, index) => {
      const jobQuery = jobQueries[index];
      const analyticsQuery = analyticsById.get(analysisId);
      return {
        analysisId,
        job: jobQuery?.data ?? null,
        analytics: analyticsQuery?.data ?? null,
        jobError: jobQuery?.isError ? normalizeApiError(jobQuery.error).message : null,
        analyticsError: analyticsQuery?.isError
          ? normalizeApiError(analyticsQuery.error).message
          : null,
      };
    });
  }, [analysisIds, analyticsIds, analyticsQueries, jobQueries]);

  return {
    analysisIds,
    records,
    summary: deriveWorkspaceSummary(records),
    isLoading:
      jobQueries.some((query) => query.isLoading) ||
      analyticsQueries.some((query) => query.isLoading),
    hasBackendError:
      jobQueries.some((query) => query.isError) ||
      analyticsQueries.some((query) => query.isError),
  };
}
