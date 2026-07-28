"use client";

import { useQuery } from "@tanstack/react-query";

import { getAnalysisHistory, getPlayHistory } from "@/lib/api/history";

export function useAnalysisHistory() {
  return useQuery({
    queryKey: ["analysis-history"],
    queryFn: () => getAnalysisHistory(),
  });
}

export function usePlayHistory() {
  return useQuery({
    queryKey: ["play-history"],
    queryFn: () => getPlayHistory(),
  });
}
