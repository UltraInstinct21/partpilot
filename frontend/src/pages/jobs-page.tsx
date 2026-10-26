import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { PlayCircle, Clock, ChevronDown, ChevronRight, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { StatusTag } from "@/components/domain/status-tag";
import { MotionGridLoader } from "@/components/motion-grid-loader";
import { useJob, useStartExtractionJob } from "@/api/hooks";
import { formatDate } from "@/lib/format";
import { toast } from "@/components/ui/toast";

// Zod schema matching extraction job endpoint contract
const extractionJobSchema = z
  .object({
    family: z.enum(["mosfet", "gate_driver"]),
    part_id: z.string().optional(),
    source_id: z.string().optional(),
    pdf_path: z.string().optional(),
    force_tier: z.string().optional(),
  })
  .refine((data) => Boolean(data.pdf_path?.trim() || data.part_id?.trim() || data.source_id?.trim()), {
    message: "Provide either a Part ID, Source ID, or PDF path",
    path: ["part_id"],
  });

type ExtractionJobForm = {
  family: "mosfet" | "gate_driver";
  part_id?: string;
  source_id?: string;
  pdf_path?: string;
  force_tier?: string;
};

export function JobsPage() {
  const [openStartDialog, setOpenStartDialog] = useState(false);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  // Tracked job IDs in session
  const [trackedJobs, setTrackedJobs] = useState<string[]>(() => {
    try {
      const saved = sessionStorage.getItem("partpilot_tracked_jobs");
      if (saved) return JSON.parse(saved);
    } catch {}
    return [];
  });

  const saveTrackedJobs = (jobs: string[]) => {
    setTrackedJobs(jobs);
    try {
      sessionStorage.setItem("partpilot_tracked_jobs", JSON.stringify(jobs));
    } catch {}
  };

  const startJob = useStartExtractionJob();

  const { register, handleSubmit, reset } = useForm<ExtractionJobForm>({
    resolver: zodResolver(extractionJobSchema) as any,
    defaultValues: {
      family: "mosfet",
      part_id: "",
      source_id: "",
      pdf_path: "",
      force_tier: "",
    },
  });

  const onSubmit = (values: ExtractionJobForm) => {
    const tier = values.force_tier ? parseInt(values.force_tier, 10) : undefined;
    const force_tier = tier === 1 || tier === 2 || tier === 3 ? (tier as 1 | 2 | 3) : undefined;
    const payload = {
      family: values.family,
      part_id: values.part_id?.trim() || undefined,
      source_id: values.source_id?.trim() || undefined,
      pdf_path: values.pdf_path?.trim() || undefined,
      force_tier,
    };

    startJob.mutate(payload, {
      onSuccess: (res) => {
        const next = [res.job_id, ...trackedJobs.filter((id) => id !== res.job_id)];
        saveTrackedJobs(next);
        setOpenStartDialog(false);
        reset();
        toast.success("Extraction job started");
      },
      onError: (err: any) => {
        toast.error(err?.message || "Failed to start extraction job");
      },
    });
  };

  return (
    <div className="space-y-6 w-full">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Clock className="size-5 text-white" />
            <h1 className="font-heading text-2xl font-semibold tracking-tight text-white">
              Extraction Pipeline Jobs
            </h1>
          </div>
          <p className="text-xs text-zinc-400 font-sans mt-1">
            Monitor real-time AI and vision parser extraction jobs processing semiconductor
            datasheets.
          </p>
        </div>

        {/* Start Extraction Dialog Trigger */}
        <Dialog open={openStartDialog} onOpenChange={setOpenStartDialog}>
          <DialogTrigger asChild>
            <Button
              size="sm"
              className="rounded-[8px] bg-white text-black hover:bg-zinc-200 text-xs font-medium shadow-none"
            >
              <PlayCircle className="size-3.5 mr-1.5" />
              Start extraction
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md rounded-[12px] border border-white/15 bg-[#18181c] text-white shadow-none">
            <DialogHeader>
              <DialogTitle className="text-white text-lg font-semibold font-heading">
                Start Extraction Job
              </DialogTitle>
              <DialogDescription className="text-zinc-400 text-xs font-sans">
                Configure the pipeline parameters to extract component specifications from
                datasheets.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-2">
              <div>
                <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-1">
                  Server-side PDF path <span className="text-red-400">*</span>
                </label>
                <input
                  {...register("pdf_path")}
                  placeholder="e.g. data/pdfs/pdf-a1b2c3.pdf"
                  className="w-full rounded-[4px] border border-white/15 bg-white/5 p-2 text-xs font-mono text-white outline-none placeholder:text-zinc-500"
                />
                <p className="mt-1 text-[11px] text-zinc-500">
                  The API runs on the server, so upload or place the PDF there first.
                </p>
              </div>

              <div>
                <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-1">
                  Target Component Family
                </label>
                <select
                  {...register("family")}
                  className="w-full rounded-[4px] border border-white/15 bg-white/5 p-2 text-xs font-mono text-white outline-none"
                >
                  <option value="mosfet" className="bg-black text-white">
                    Power MOSFET
                  </option>
                  <option value="gate_driver" className="bg-black text-white">
                    Gate Driver IC
                  </option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-1">
                  Component Part ID (Optional)
                </label>
                <input
                  {...register("part_id")}
                  placeholder="e.g. mosfet-irf3205s"
                  className="w-full rounded-[4px] border border-white/15 bg-white/5 p-2 text-xs font-mono text-white outline-none placeholder:text-zinc-500"
                />
              </div>

              <div>
                <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-1">
                  Source ID (Optional)
                </label>
                <input
                  {...register("source_id")}
                  placeholder="e.g. pdf-a1b2c3..."
                  className="w-full rounded-[4px] border border-white/15 bg-white/5 p-2 text-xs font-mono text-white outline-none placeholder:text-zinc-500"
                />
              </div>

              <div>
                <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-1">
                  Force Pipeline Tier (Optional)
                </label>
                <select
                  {...register("force_tier")}
                  className="w-full rounded-[4px] border border-white/15 bg-white/5 p-2 text-xs font-mono text-white outline-none"
                >
                  <option value="" className="bg-black text-white">
                    Autonomous (Cascading Tier 1 to 3)
                  </option>
                  <option value="1" className="bg-black text-white">
                    Force Tier 1 (Rule-based table parser)
                  </option>
                  <option value="2" className="bg-black text-white">
                    Force Tier 2 (LLM text extraction)
                  </option>
                  <option value="3" className="bg-black text-white">
                    Force Tier 3 (Multimodal vision)
                  </option>
                </select>
              </div>

              <DialogFooter className="pt-2 flex items-center justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setOpenStartDialog(false)}
                  className="text-xs rounded-[8px] border-white/15 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10 shadow-none"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={startJob.isPending}
                  className="text-xs rounded-[8px] bg-white text-black hover:bg-zinc-200 shadow-none inline-flex items-center gap-1.5"
                >
                  {startJob.isPending ? (
                    <>
                      <MotionGridLoader size="xs" variant="default" />
                      <span>Queuing job...</span>
                    </>
                  ) : (
                    <span>Start job</span>
                  )}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Tracked Jobs List - Clean unboxed list */}
      <div className="space-y-4 w-full">
        <div className="border-b border-white/10 pb-3">
          <h2 className="text-sm font-semibold text-white font-heading">Active & Recent Jobs</h2>
          <p className="text-xs text-zinc-400">
            Real-time pipeline extraction progress. Automatically pauses polling when tab is
            inactive.
          </p>
        </div>

        <div>
          {trackedJobs.length === 0 ? (
            <div className="py-16 text-center text-xs text-zinc-500 border-b border-white/10">
              <p className="font-medium text-white mb-1">No jobs yet.</p>
              <p className="text-zinc-400 mb-4">Start an extraction to add parts.</p>
              <Button
                size="sm"
                onClick={() => setOpenStartDialog(true)}
                className="text-xs rounded-[6px] bg-white text-black hover:bg-zinc-200 shadow-none cursor-pointer"
              >
                Start an extraction
              </Button>
            </div>
          ) : (
            <div className="divide-y divide-white/10 border-b border-white/10">
              {trackedJobs.map((jobId) => (
                <JobRowItem
                  key={jobId}
                  jobId={jobId}
                  isExpanded={expandedJobId === jobId}
                  onToggle={() => setExpandedJobId((prev) => (prev === jobId ? null : jobId))}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function JobRowItem({
  jobId,
  isExpanded,
  onToggle,
}: {
  jobId: string;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const jobQuery = useJob(jobId);
  const job = jobQuery.data;

  const state = job?.state ?? "queued";
  const progressPercent =
    job && job.total && job.total > 0 && job.progress !== undefined
      ? Math.min(100, Math.round((job.progress / job.total) * 100))
      : state === "completed"
        ? 100
        : 10;

  return (
    <div className="py-3">
      <div
        onClick={onToggle}
        className="flex flex-wrap items-center justify-between gap-3 cursor-pointer select-none"
      >
        <div className="flex items-center gap-3">
          <button type="button" aria-label="Toggle details" className="text-zinc-400">
            {isExpanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-semibold text-white">{jobId}</span>
              <StatusTag status={state} type="generic" />
            </div>
            <div className="text-[11px] font-mono text-zinc-400 mt-0.5">
              Scope: {job?.part_id || "Full Catalog Batch"} | Kind: {job?.kind || "extract"}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="w-36 hidden sm:block space-y-1">
            <div className="flex justify-between items-center text-[10px] text-zinc-400">
              <span className="flex items-center gap-1.5">
                {(state === "running" || state === "queued") && (
                  <MotionGridLoader size="xs" />
                )}
                Progress
              </span>
              <span className="text-zinc-200">{progressPercent}%</span>
            </div>
            <Progress value={progressPercent} className="h-1.5 bg-white/10" />
          </div>

          <div className="text-right text-[11px] text-zinc-400 hidden md:block">
            {job?.created_at ? formatDate(job.created_at) : "Just now"}
          </div>
        </div>
      </div>

      {/* Expanded Row Detail */}
      {isExpanded && (
        <div className="mt-3 ml-7 rounded-[8px] border border-white/10 bg-white/5 p-4 text-xs font-mono text-zinc-300">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
            <div>
              <span className="text-zinc-400">Message: </span>
              <span className="text-white">
                {job?.message || "Job queued for pipeline execution"}
              </span>
            </div>
            <div>
              <span className="text-zinc-400">Processed Items: </span>
              <span className="text-white">
                {job?.progress ?? 0} / {job?.total ?? 1}
              </span>
            </div>
            {job?.source_id && (
              <div>
                <span className="text-zinc-400">Source: </span>
                <span className="text-white">{job.source_id}</span>
              </div>
            )}
            {job?.updated_at && (
              <div>
                <span className="text-zinc-400">Updated: </span>
                <span className="text-white">{formatDate(job.updated_at)}</span>
              </div>
            )}
          </div>

          {state === "failed" && (
            <div className="rounded-[4px] border border-red-500/20 bg-red-500/10 p-3 text-xs mb-3 flex items-start justify-between gap-4">
              <div className="flex items-start gap-2">
                <AlertCircle className="size-4 shrink-0 text-red-400 mt-0.5" />
                <div>
                  <div className="font-semibold text-white">Extraction failed</div>
                  <div className="text-zinc-400 mt-0.5">
                    {job?.error || "Pipeline step encountered an unrecoverable parser error."}
                  </div>
                </div>
              </div>
              <span className="text-[11px] text-zinc-500">
                Start a new job with a valid PDF path.
              </span>
            </div>
          )}

          {job?.result && (
            <div className="mt-2 pt-2 border-t border-white/10 text-[11px]">
              <span className="font-semibold text-white block mb-1">Pipeline Results Summary:</span>
              <pre className="bg-black/40 border border-white/10 p-2 rounded-[4px] overflow-x-auto text-[10px] text-zinc-300">
                {JSON.stringify(job.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
