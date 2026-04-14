type ApprovalActionsProps = {
  disabled?: boolean;
  loading?: boolean;
  onApprove: () => void;
  onReject: () => void;
};

export function ApprovalActions({ disabled, loading, onApprove, onReject }: ApprovalActionsProps) {
  return (
    <div className="flex flex-wrap gap-3">
      <button
        type="button"
        disabled={disabled || loading}
        onClick={onApprove}
        className="border-2 border-primary bg-primary px-5 py-3 font-mono text-sm uppercase tracking-[0.25em] text-text disabled:cursor-not-allowed disabled:border-text disabled:bg-bg"
      >
        {loading ? "Processing" : "Approve"}
      </button>
      <button
        type="button"
        disabled={disabled || loading}
        onClick={onReject}
        className="border-2 border-danger bg-danger px-5 py-3 font-mono text-sm uppercase tracking-[0.25em] text-text disabled:cursor-not-allowed disabled:border-text disabled:bg-bg"
      >
        Reject
      </button>
    </div>
  );
}
