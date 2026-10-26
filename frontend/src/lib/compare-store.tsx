import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { MAX_COMPARE_PARTS } from "./constants";

export interface ComparePartItem {
  id: string;
  mpn: string;
}

interface CompareContextValue {
  selectedParts: ComparePartItem[];
  addPart: (part: ComparePartItem) => boolean;
  removePart: (id: string) => void;
  togglePart: (part: ComparePartItem) => void;
  clear: () => void;
  clearParts: () => void;
  isSelected: (id: string) => boolean;
}

const STORAGE_KEY = "partpilot_compare_selection";

const CompareContext = createContext<CompareContextValue | null>(null);

function loadInitialParts(): ComparePartItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.slice(0, MAX_COMPARE_PARTS);
    }
  } catch {
    // LocalStorage failure or corrupted data
  }
  return [];
}

export function CompareProvider({ children }: { children: ReactNode }) {
  const [selectedParts, setSelectedParts] = useState<ComparePartItem[]>(loadInitialParts);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedParts));
    } catch {
      // Ignore localStorage errors (e.g. private browsing or full quota)
    }
  }, [selectedParts]);

  const addPart = (part: ComparePartItem): boolean => {
    if (selectedParts.some((p) => p.id === part.id)) {
      return true;
    }
    if (selectedParts.length >= MAX_COMPARE_PARTS) {
      toast("Compare supports up to 4 parts. Remove one to add another.");
      return false;
    }
    setSelectedParts((prev) => [...prev, part]);
    return true;
  };

  const removePart = (id: string) => {
    setSelectedParts((prev) => prev.filter((p) => p.id !== id));
  };

  const togglePart = (part: ComparePartItem) => {
    if (selectedParts.some((p) => p.id === part.id)) {
      removePart(part.id);
    } else {
      addPart(part);
    }
  };

  const clear = () => {
    setSelectedParts([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore localStorage errors
    }
  };

  const isSelected = (id: string) => selectedParts.some((p) => p.id === id);

  return (
    <CompareContext.Provider
      value={{ selectedParts, addPart, removePart, togglePart, clear, clearParts: clear, isSelected }}
    >
      {children}
    </CompareContext.Provider>
  );
}

export function useCompareSelection() {
  const ctx = useContext(CompareContext);
  if (!ctx) {
    throw new Error("useCompareSelection must be used within CompareProvider");
  }
  return ctx;
}
