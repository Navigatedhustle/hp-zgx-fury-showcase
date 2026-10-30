import { AlertTriangle } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button, Empty } from "./ui";

interface Props {
  children: ReactNode;
  /** Changing this resets the boundary — pass the route or record being shown. */
  resetKey?: string;
  title?: string;
}
interface State { error: Error | null; key?: string }

/**
 * Catches render throws so one bad field in a server payload can't take the
 * whole app down. React has no hook equivalent; a class is the only way.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    if (state.key !== props.resetKey) return { key: props.resetKey, error: null };
    return null;
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Render failed", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <Empty
        icon={<AlertTriangle className="size-5 text-bad" />}
        title={this.props.title ?? "This view hit a snag"}
        body={`${error.message || "Something in the response wasn't what the page expected."} Your work is safe on the server — try again, or reload the page.`}
        action={
          <div className="flex gap-2">
            <Button variant="primary" onClick={() => this.setState({ error: null })}>Try again</Button>
            <Button onClick={() => window.location.reload()}>Reload the page</Button>
          </div>
        }
      />
    );
  }
}
