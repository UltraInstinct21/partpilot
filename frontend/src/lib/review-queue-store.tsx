import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

export interface ReviewQueueItem {
  id: string; // part_id
  mpn: string;
  manufacturer: string;
  family: string;
  package?: string;
  description?: string;
  lifecycle_status?: string;
  parameters?: Record<string, any>;
  stock?: number;
  price?: number;
  currency?: string;
  datasheet_url?: string;
  status: "candidate" | "finalized" | "rejected";
  referenceDesignator: string;
  targetSubsystem: string;
  notes: string;
  addedAt: string;
}

interface ReviewQueueContextValue {
  items: ReviewQueueItem[];
  addItem: (
    part: any,
    meta?: Partial<Pick<ReviewQueueItem, "referenceDesignator" | "targetSubsystem" | "notes" | "status">>,
  ) => boolean;
  removeItem: (id: string) => void;
  toggleItem: (part: any) => void;
  isInQueue: (id: string) => boolean;
  finalizeItem: (id: string) => void;
  unfinalizeItem: (id: string) => void;
  rejectItem: (id: string) => void;
  updateItemMeta: (
    id: string,
    meta: Partial<Pick<ReviewQueueItem, "referenceDesignator" | "targetSubsystem" | "notes" | "status">>,
  ) => void;
  finalizeAll: () => void;
  clearQueue: () => void;
  loadSampleCandidates: () => void;
  finalizedItems: ReviewQueueItem[];
  candidateItems: ReviewQueueItem[];
  finalizedCount: number;
  totalCount: number;
}

const STORAGE_KEY = "partpilot_review_queue_parts";

const SAMPLE_PARTS: ReviewQueueItem[] = [
  {
    id: "mosfet-irf3205s",
    mpn: "IRF3205S",
    manufacturer: "Infineon Technologies",
    family: "mosfet",
    package: "D2PAK",
    description: "55V Single N-Channel HEXFET Power MOSFET in a D2Pak package, 110A, 8.0 mΩ",
    lifecycle_status: "active",
    parameters: {
      vds_max: 55,
      id_max: 110,
      rds_on: 8.0,
      qg_typ: 146,
    },
    stock: 4500,
    price: 1.45,
    currency: "USD",
    datasheet_url: "https://www.infineon.com/dgdl/irf3205spbf.pdf",
    status: "finalized",
    referenceDesignator: "Q1",
    targetSubsystem: "Synchronous Buck Low-Side",
    notes: "Primary low-side power switch. 8mΩ ensures minimal conduction losses.",
    addedAt: new Date().toISOString(),
  },
  {
    id: "mosfet-ipb014n08n5",
    mpn: "IPB014N08N5",
    manufacturer: "Infineon Technologies",
    family: "mosfet",
    package: "PG-TO263-7",
    description: "OptiMOS 5 Power-Transistor 80V, 180A, 1.4 mΩ",
    lifecycle_status: "active",
    parameters: {
      vds_max: 80,
      id_max: 180,
      rds_on: 1.4,
      qg_typ: 178,
    },
    stock: 2800,
    price: 3.20,
    currency: "USD",
    datasheet_url: "https://www.infineon.com/dgdl/Infineon-IPB014N08N5-DS-v02_01-EN.pdf",
    status: "candidate",
    referenceDesignator: "Q2",
    targetSubsystem: "Battery Protection Disconnect",
    notes: "Ultra-low Rds(on) alternative for minimum dissipation under 100A continuous.",
    addedAt: new Date().toISOString(),
  },
  {
    id: "gate-driver-ncp51820",
    mpn: "NCP51820",
    manufacturer: "onsemi",
    family: "gate_driver",
    package: "QFN-15",
    description: "High-Speed, 650 V, GaN Half-Bridge Gate Driver with integrated bootstrap diode",
    lifecycle_status: "active",
    parameters: {
      vcc_max: 20,
      iout_peak: 2.0,
      tpd_ns: 25,
      channels: 2,
    },
    stock: 6200,
    price: 2.15,
    currency: "USD",
    datasheet_url: "https://www.onsemi.com/pdf/datasheet/ncp51820-d.pdf",
    status: "finalized",
    referenceDesignator: "U1",
    targetSubsystem: "Half-Bridge Gate Drive",
    notes: "Fast 25ns propagation delay matched for high-frequency switching.",
    addedAt: new Date().toISOString(),
  },
];

function loadInitialItems(): ReviewQueueItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed;
    }
  } catch {
    // LocalStorage failure or corrupted data
  }
  return [];
}

const ReviewQueueContext = createContext<ReviewQueueContextValue | null>(null);

export function ReviewQueueProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ReviewQueueItem[]>(loadInitialItems);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {
      // Ignore localStorage errors
    }
  }, [items]);

  const isInQueue = (id: string) => items.some((item) => item.id === id);

  const addItem = (
    part: any,
    meta?: Partial<Pick<ReviewQueueItem, "referenceDesignator" | "targetSubsystem" | "notes" | "status">>,
  ): boolean => {
    const partId = part.part_id || part.id || `part-${part.mpn.toLowerCase().replace(/[^a-z0-9]/g, "-")}`;
    if (items.some((item) => item.id === partId)) {
      toast.info(`${part.mpn} is already in your Review Queue.`);
      return true;
    }

    // Extract parameters
    const params: Record<string, any> = {};
    if (part.key_parameters) {
      Object.assign(params, part.key_parameters);
    }
    if (Array.isArray(part.parameters)) {
      for (const p of part.parameters) {
        if (p?.name) params[p.name] = p.value ?? p.value_text;
      }
    } else if (part.parameters && typeof part.parameters === "object") {
      Object.assign(params, part.parameters);
    }

    // Best stock & price
    let stock = part.stock ?? 0;
    let price = part.unit_price ?? part.price ?? 0;
    let currency = part.currency || "USD";

    if (Array.isArray(part.offers) && part.offers.length > 0) {
      const totalStock = part.offers.reduce((acc: number, off: any) => acc + (off.stock || 0), 0);
      if (totalStock > 0) stock = totalStock;
      const validPrices = part.offers.filter((off: any) => off.unit_price > 0);
      if (validPrices.length > 0) {
        price = validPrices[0].unit_price;
        currency = validPrices[0].currency || "USD";
      }
    }

    const nextIndex = items.length + 1;
    const prefix = (part.family === "mosfet" || part.family === "transistor") ? "Q" : (part.family === "gate_driver" || part.family === "mcu" || part.family === "opamp") ? "U" : "IC";

    const newItem: ReviewQueueItem = {
      id: partId,
      mpn: part.mpn,
      manufacturer: part.manufacturer || "Unknown Manufacturer",
      family: part.family || "general",
      package: part.package,
      description: part.description,
      lifecycle_status: part.lifecycle_status || "active",
      parameters: params,
      stock,
      price,
      currency,
      datasheet_url: part.datasheet_url,
      status: meta?.status || "candidate",
      referenceDesignator: meta?.referenceDesignator || `${prefix}${nextIndex}`,
      targetSubsystem: meta?.targetSubsystem || "Main System",
      notes: meta?.notes || "",
      addedAt: new Date().toISOString(),
    };

    setItems((prev) => [...prev, newItem]);
    toast.success(`Added ${part.mpn} to Review Queue`, {
      description: "Ready for AI tradeoff analysis and final BOM export.",
    });
    return true;
  };

  const removeItem = (id: string) => {
    setItems((prev) => prev.filter((p) => p.id !== id));
  };

  const toggleItem = (part: any) => {
    const partId = part.part_id || part.id || `part-${part.mpn.toLowerCase().replace(/[^a-z0-9]/g, "-")}`;
    if (isInQueue(partId)) {
      removeItem(partId);
      toast.info(`Removed ${part.mpn} from Review Queue`);
    } else {
      addItem(part);
    }
  };

  const finalizeItem = (id: string) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, status: "finalized" } : item)),
    );
    const it = items.find((p) => p.id === id);
    if (it) {
      toast.success(`${it.mpn} marked as Finalized`, {
        description: "Approved for production BOM export.",
      });
    }
  };

  const unfinalizeItem = (id: string) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, status: "candidate" } : item)),
    );
  };

  const rejectItem = (id: string) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, status: "rejected" } : item)),
    );
  };

  const updateItemMeta = (
    id: string,
    meta: Partial<Pick<ReviewQueueItem, "referenceDesignator" | "targetSubsystem" | "notes" | "status">>,
  ) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, ...meta } : item)),
    );
  };

  const finalizeAll = () => {
    setItems((prev) => prev.map((item) => ({ ...item, status: "finalized" })));
    toast.success("All components marked as Finalized for BOM export.");
  };

  const clearQueue = () => {
    setItems([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore
    }
    toast.info("Review Queue cleared.");
  };

  const loadSampleCandidates = () => {
    setItems(SAMPLE_PARTS);
    toast.success("Loaded sample component design candidates into Review Queue.");
  };

  const finalizedItems = items.filter((item) => item.status === "finalized");
  const candidateItems = items.filter((item) => item.status === "candidate");

  return (
    <ReviewQueueContext.Provider
      value={{
        items,
        addItem,
        removeItem,
        toggleItem,
        isInQueue,
        finalizeItem,
        unfinalizeItem,
        rejectItem,
        updateItemMeta,
        finalizeAll,
        clearQueue,
        loadSampleCandidates,
        finalizedItems,
        candidateItems,
        finalizedCount: finalizedItems.length,
        totalCount: items.length,
      }}
    >
      {children}
    </ReviewQueueContext.Provider>
  );
}

export function useReviewQueueStore() {
  const ctx = useContext(ReviewQueueContext);
  if (!ctx) {
    throw new Error("useReviewQueueStore must be used within ReviewQueueProvider");
  }
  return ctx;
}
