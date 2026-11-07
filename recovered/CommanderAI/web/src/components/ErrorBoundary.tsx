import { Alert, Button, Code, Stack, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/** Keeps a crash in one page from blanking the whole app. Reset when `resetKey` changes. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error", error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Alert
        color="red"
        variant="light"
        icon={<IconAlertTriangle />}
        title="This page hit a problem"
        role="alert"
      >
        <Stack gap="xs">
          <Text size="sm">
            Something went wrong while showing this page. Other pages still work.
          </Text>
          <Code block>{this.state.error.message}</Code>
          <Button
            size="xs"
            variant="light"
            color="red"
            w="fit-content"
            onClick={() => window.location.reload()}
          >
            Reload the page
          </Button>
        </Stack>
      </Alert>
    );
  }
}
