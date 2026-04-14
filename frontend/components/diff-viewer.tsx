type DiffViewerProps = {
  diff: string;
};

export function DiffViewer({ diff }: DiffViewerProps) {
  return (
    <pre className="max-h-[40rem] overflow-auto border-2 border-text bg-bg p-5 font-mono text-sm leading-7 text-text">
      {diff || "No diff available for this action."}
    </pre>
  );
}
