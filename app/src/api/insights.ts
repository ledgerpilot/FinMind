import { api } from './client';

export type BudgetSuggestion = {
  month: string;
  suggested_total: number;
  breakdown: {
    needs: number;
    wants: number;
    savings: number;
  };
  tips?: string[];
  analytics: {
    month_over_month_change_pct: number;
    current_month_expenses: number;
    previous_month_expenses: number;
    top_categories: Array<{ category_id: string; amount: number }>;
  };
  persona?: string;
  method: 'gemini' | 'heuristic' | string;
  warnings?: string[];
  net_flow?: number;
};

export type WeeklySummary = {
  week_start: string; // YYYY-MM-DD (Monday)
  total_spending: number;
  income: number;
  net_flow: number;
  top_categories: Array<{ category_id: string; amount: number }>;
  week_over_week_change_pct: number;
  insights: string[];
  persona?: string;
  method: 'gemini' | 'heuristic' | 'heuristic_fallback' | string;
};

export async function getBudgetSuggestion(params?: {
  month?: string;
  geminiApiKey?: string;
  persona?: string;
}): Promise<BudgetSuggestion> {
  const monthQuery = params?.month ? `?month=${encodeURIComponent(params.month)}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<BudgetSuggestion>(`/insights/budget-suggestion${monthQuery}`, { headers });
}

export async function getWeeklySummary(params?: {
  week?: string; // YYYY-MM-DD (Monday)
  geminiApiKey?: string;
  persona?: string;
}): Promise<WeeklySummary> {
  const weekQuery = params?.week ? `?week=${encodeURIComponent(params.week)}` : '';
  const headers: Record<string, string> = {};
  if (params?.geminiApiKey) headers['X-Gemini-Api-Key'] = params.geminiApiKey;
  if (params?.persona) headers['X-Insight-Persona'] = params.persona;
  return api<WeeklySummary>(`/insights/weekly-summary${weekQuery}`, { headers });
}
