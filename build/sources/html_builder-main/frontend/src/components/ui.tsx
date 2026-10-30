import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Loader2, X } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { cn } from "../lib/util";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "room";
const variants: Record<Variant, string> = {
  primary: "bg-accent text-accent-ink hover:brightness-110 shadow-sm disabled:opacity-50",
  secondary: "bg-surface text-ink border border-line hover:border-faint disabled:opacity-50",
  ghost: "text-muted hover:text-ink hover:bg-surface-2 disabled:opacity-40",
  danger: "bg-bad text-white hover:brightness-110 disabled:opacity-50",
  room: "bg-room-2 text-room-ink border border-room-line hover:border-room-muted disabled:opacity-40",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest }, ref) {
  const sizes = { sm: "h-8 px-3 text-[13px] gap-1.5", md: "h-9 px-3.5 text-sm gap-2", lg: "h-11 px-5 text-[15px] gap-2" };
  return (
    <button ref={ref} disabled={disabled || loading}
      className={cn("inline-flex items-center justify-center rounded-lg font-semibold whitespace-nowrap transition-colors select-none disabled:cursor-not-allowed",
        variants[variant], sizes[size], className)} {...rest}>
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

export function IconButton({ label, className, children, variant = "ghost", ...rest }: ButtonProps & { label: string }) {
  return (
    <Tip label={label}>
      <button aria-label={label}
        className={cn("inline-flex size-8 items-center justify-center rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
          variants[variant], className)} {...rest}>
        {children}
      </button>
    </Tip>
  );
}

export function Tip({ label, children, side = "top" }: { label: ReactNode; children: ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <TooltipPrimitive.Root delayDuration={300}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content side={side} sideOffset={6}
          className="z-50 max-w-xs rounded-md bg-ink px-2.5 py-1.5 text-xs font-medium text-canvas shadow-card">
          {label}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-4 animate-spin", className)} />;
}

export function Switch({ checked, onCheckedChange, label, disabled }: { checked: boolean; onCheckedChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <SwitchPrimitive.Root checked={checked} onCheckedChange={onCheckedChange} aria-label={label} disabled={disabled}
      className="relative h-5 w-9 shrink-0 rounded-full bg-line transition-colors data-[state=checked]:bg-accent disabled:opacity-50">
      <SwitchPrimitive.Thumb className="block size-4 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
    </SwitchPrimitive.Root>
  );
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cn("w-full resize-none rounded-lg border border-line bg-surface px-3 py-2.5 text-sm leading-relaxed text-ink placeholder:text-faint focus:border-accent focus:outline-none", className)} {...rest} />;
});

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-semibold text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputClass = "h-9 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none";

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-line bg-surface-2 px-1 text-[11px] font-semibold text-muted">{children}</kbd>;
}

export type Tone = "good" | "warn" | "bad" | "busy" | "idle" | "accent";
const tones: Record<Tone, string> = {
  good: "bg-good-soft text-good",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  busy: "bg-accent-soft text-accent",
  idle: "bg-surface-2 text-muted",
  accent: "bg-accent text-accent-ink",
};
export function Badge({ tone = "idle", children, className, pulse }: { tone?: Tone; children: ReactNode; className?: string; pulse?: boolean }) {
  return (
    <span className={cn("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold whitespace-nowrap", tones[tone], className)}>
      {pulse && <span className="relative flex size-1.5"><span className="absolute inline-flex size-full animate-ping rounded-full bg-current opacity-60" /><span className="relative inline-flex size-1.5 rounded-full bg-current" /></span>}
      {children}
    </span>
  );
}

export function Dialog({ open, onOpenChange, title, description, children, wide, footer }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: string; children?: ReactNode; wide?: boolean; footer?: ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-[2px] data-[state=open]:animate-in" />
        <DialogPrimitive.Content className={cn("fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl border border-line bg-surface p-6 shadow-card",
          wide ? "max-w-5xl" : "max-w-md")}>
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <DialogPrimitive.Title className="text-lg font-bold tracking-tight">{title}</DialogPrimitive.Title>
              {description && <DialogPrimitive.Description className="mt-1 text-sm text-muted">{description}</DialogPrimitive.Description>}
            </div>
            <DialogPrimitive.Close asChild><IconButton label="Close"><X className="size-4" /></IconButton></DialogPrimitive.Close>
          </div>
          {children}
          {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function Empty({ icon, title, body, action }: { icon: ReactNode; title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-4 flex size-12 items-center justify-center rounded-xl bg-surface-2 text-muted">{icon}</div>
      <h3 className="text-base font-bold">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-muted">{body}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
