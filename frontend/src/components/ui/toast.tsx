import * as React from "react";
import { Toast } from "@animate-ui/react/primitives/base-ui/toast";
import { Check, AlertCircle, AlertTriangle, Info, X } from "lucide-react";
import { MotionGridLoader } from "@/components/motion-grid-loader";
import { cn } from "@/lib/utils";

// Create a single global toast manager for dispatching toasts from anywhere in the application
export const toastManager = Toast.createToastManager();

export interface ToastOptions {
  id?: string;
  description?: React.ReactNode;
  type?: "success" | "error" | "info" | "warning" | "loading";
  timeout?: number;
  priority?: "low" | "high";
  actionProps?: React.ComponentPropsWithoutRef<"button">;
  onClose?: () => void;
  onRemove?: () => void;
  [key: string]: unknown;
}

export type ToastTitleOrOptions = React.ReactNode | (ToastOptions & { title?: React.ReactNode });

/**
 * Imperative toast notification dispatcher matching Sonner and Base UI conventions.
 */
function createToastFn() {
  const fn = (titleOrOptions: ToastTitleOrOptions, options?: ToastOptions) => {
    if (React.isValidElement(titleOrOptions) || typeof titleOrOptions === "string" || typeof titleOrOptions === "number") {
      const id = options?.id || (typeof titleOrOptions === "string" ? titleOrOptions : undefined);
      return toastManager.add({
        id,
        title: titleOrOptions,
        ...options,
      });
    }
    return toastManager.add(titleOrOptions as unknown as Parameters<typeof toastManager.add>[0]);
  };

  return Object.assign(fn, {
    success: (title: React.ReactNode, options?: ToastOptions) => {
      const id = options?.id || (typeof title === "string" ? `success-${title}` : undefined);
      return toastManager.add({
        id,
        title,
        type: "success",
        ...options,
      });
    },
    error: (title: React.ReactNode, options?: ToastOptions) => {
      const id = options?.id || (typeof title === "string" ? `error-${title}` : undefined);
      return toastManager.add({
        id,
        title,
        type: "error",
        ...options,
      });
    },
    info: (title: React.ReactNode, options?: ToastOptions) => {
      const id = options?.id || (typeof title === "string" ? `info-${title}` : undefined);
      return toastManager.add({
        id,
        title,
        type: "info",
        ...options,
      });
    },
    warning: (title: React.ReactNode, options?: ToastOptions) => {
      const id = options?.id || (typeof title === "string" ? `warning-${title}` : undefined);
      return toastManager.add({
        id,
        title,
        type: "warning",
        ...options,
      });
    },
    loading: (title: React.ReactNode, options?: ToastOptions) => {
      const id = options?.id || (typeof title === "string" ? `loading-${title}` : undefined);
      return toastManager.add({
        id,
        title,
        type: "loading",
        timeout: 0,
        ...options,
      });
    },
    promise: <T,>(
      promiseValue: Promise<T>,
      options: {
        loading: React.ReactNode | ToastOptions;
        success: React.ReactNode | ToastOptions | ((val: T) => React.ReactNode | ToastOptions);
        error: React.ReactNode | ToastOptions | ((err: unknown) => React.ReactNode | ToastOptions);
      }
    ) => {
      const normalize = (val: unknown) =>
        typeof val === "string" || React.isValidElement(val) ? { title: val as React.ReactNode } : (val as ToastOptions);

      return toastManager.promise(promiseValue, {
        loading: normalize(options.loading) as Parameters<typeof toastManager.promise>[1]["loading"],
        success: ((result: T) =>
          normalize(typeof options.success === "function" ? options.success(result) : options.success)) as Parameters<typeof toastManager.promise>[1]["success"],
        error: ((err: unknown) =>
          normalize(typeof options.error === "function" ? options.error(err) : options.error)) as Parameters<typeof toastManager.promise>[1]["error"],
      });
    },
    dismiss: (id?: string) => toastManager.close(id),
    close: (id?: string) => toastManager.close(id),
    update: (id: string, updates: Parameters<typeof toastManager.update>[1]) => toastManager.update(id, updates),
  });
}

export const toast = createToastFn();

/** Status icon rendered inside data-slot="toast-icon" */
function ToastStatusIcon({ type }: { type?: string }) {
  if (!type) return null;
  return (
    <div
      data-slot="toast-icon"
      className="mt-0.5 flex size-4 shrink-0 items-center justify-center text-white select-none"
    >
      {type === "success" && <Check className="size-3.5 text-white" />}
      {type === "error" && <AlertCircle className="size-3.5 text-white" />}
      {type === "warning" && <AlertTriangle className="size-3.5 text-white" />}
      {type === "info" && <Info className="size-3.5 text-white" />}
      {type === "loading" && <MotionGridLoader size="xs" variant="default" />}
    </div>
  );
}

function ToastList() {
  const { toasts } = Toast.useToastManager();

  return (
    <>
      {toasts.map((item) => (
        <Toast.Root
          key={item.id}
          toast={item}
          className={cn(
            "group pointer-events-auto relative flex w-full items-start justify-between gap-3 overflow-hidden rounded-[8px] border border-white/20 bg-black/95 p-3.5 pr-8 text-white shadow-2xl backdrop-blur-md"
          )}
        >
          <Toast.Content className="flex w-full items-start gap-2.5">
            <ToastStatusIcon type={item.type} />
            <div className="flex-1 min-w-0">
              <Toast.Title className="text-xs font-mono font-medium text-white leading-tight" />
              <Toast.Description className="text-[11px] font-mono text-zinc-400 mt-1 leading-normal" />
            </div>
          </Toast.Content>
          <Toast.Close
            aria-label="Close"
            className="absolute right-2.5 top-2.5 rounded-[4px] p-1 text-zinc-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            <X className="size-3" />
          </Toast.Close>
        </Toast.Root>
      ))}
    </>
  );
}

export interface ToasterProps {
  children?: React.ReactNode;
  progressBar?: boolean;
  timeout?: number;
  limit?: number;
}

/**
 * Animated Toast notification provider and viewport using Animate UI / Base UI.
 */
export function Toaster({
  children,
  progressBar = true,
  timeout = 4000,
  limit = 4,
}: ToasterProps) {
  return (
    <Toast.Provider
      toastManager={toastManager}
      progressBar={progressBar}
      timeout={timeout}
      limit={limit}
    >
      {children}
      <Toast.Portal>
        <Toast.Viewport className="fixed bottom-0 right-0 z-[100] flex max-h-screen w-full flex-col-reverse p-4 sm:bottom-4 sm:right-4 sm:top-auto sm:flex-col md:max-w-[400px] gap-2 outline-none pointer-events-none">
          <ToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  );
}

export { Toast };
