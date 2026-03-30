import { Button } from "@heroui/react";
import type { ReactNode } from "react";
import { Component } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    message: "",
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      message: error.message || "Unexpected UI error",
    };
  }

  componentDidCatch(error: Error) {
    console.error("SMIF UI render failure", error);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="grid min-h-screen place-items-center bg-[radial-gradient(circle_at_top,_#dff6ea,_#f6f2e9_45%,_#f2ede2_100%)] p-6 text-slate-950">
          <div className="grid max-w-xl gap-4 rounded-[2rem] border border-rose-200 bg-white p-8 shadow-[0_20px_80px_rgba(15,23,42,0.08)]">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.25em] text-rose-700">
                UI Error
              </p>
              <h1 className="mt-2 text-2xl font-semibold">The page hit a render failure.</h1>
            </div>
            <p className="text-sm text-slate-600">{this.state.message}</p>
            <div>
              <Button variant="primary" onPress={this.handleReload}>
                Reload Page
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
