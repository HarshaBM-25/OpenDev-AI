type StatusPillProps = {
  label: string;
  tone?: "primary" | "danger" | "neutral" | "warning" | "success";
};

export function StatusPill({ label, tone = "neutral" }: StatusPillProps) {
  const cls =
    tone === "primary"
      ? "border-primary bg-primary text-white"
      : tone === "danger"
      ? "border-danger bg-danger text-white"
      : tone === "warning"
      ? "border-[#b45309] bg-[#fbbf24] text-text"
      : tone === "success"
      ? "border-[#15803d] bg-[#bbf7d0] text-text"
      : "border-text bg-bg text-text";

  return (
    <span className={`inline-flex border-2 px-3 py-1 font-mono text-xs uppercase tracking-[0.25em] ${cls}`}>
      {label}
    </span>
  );
}
