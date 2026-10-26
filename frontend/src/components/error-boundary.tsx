import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertCircle, RotateCcw, Search } from "lucide-react";
import { Link } from "react-router-dom";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("PartPilot interface uncaught error:", error, errorInfo);
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[60vh] items-center justify-center p-6 text-center w-full">
          <div className="w-full max-w-md rounded-[12px] bg-[#121215] text-white p-8 border border-white/10 shadow-none">
            <div className="flex justify-center mb-4">
              <AlertCircle className="size-8 text-white stroke-[1.5]" />
            </div>
            <h1 className="font-heading text-lg font-semibold text-white mb-2">
              An unexpected error occurred
            </h1>
            <p className="text-xs text-zinc-400 mb-6">
              {this.state.error?.message || "The application encountered a problem rendering this view."}
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <button
                type="button"
                onClick={this.handleRetry}
                className="inline-flex items-center gap-2 rounded-[8px] border border-white bg-white px-4 py-2 text-xs font-medium text-black hover:bg-zinc-200 transition-none"
              >
                <RotateCcw className="size-3.5" />
                Retry
              </button>
              <Link
                to="/search"
                onClick={() => this.setState({ hasError: false, error: null })}
                className="inline-flex items-center gap-2 rounded-[8px] border border-white/20 bg-transparent px-4 py-2 text-xs font-medium text-white hover:bg-white/10 transition-none"
              >
                <Search className="size-3.5" />
                Return to Search
              </Link>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
