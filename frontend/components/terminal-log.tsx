import { LogEntry } from "@/lib/types";

type TerminalLogProps = {
  logs: LogEntry[];
};

export function TerminalLog({ logs }: TerminalLogProps) {
  const content =
    logs.length > 0
      ? logs
          .map((entry) => {
            const timestamp = new Date(entry.timestamp).toLocaleString();
            return `[${timestamp}] [${entry.level.toUpperCase()}] [${entry.step}] ${entry.message}`;
          })
          .join("\n")
      : "No execution logs yet.";

  return (
    <pre className="max-h-[36rem] overflow-auto border-2 border-primary bg-bg p-5 font-mono text-sm leading-7 text-text">
      {content}
    </pre>
  );
}
