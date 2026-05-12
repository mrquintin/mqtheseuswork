"use client";

import { forwardRef } from "react";
import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  ReactNode,
} from "react";

/**
 * Shared button vocabulary for workflow surfaces.
 *
 * Visual ladder, quietest to loudest:
 *   variant="ghost"   — no border, amber text, used inline
 *   variant="quiet"   — bordered, sentence-case, no Cinzel
 *   variant="default" — the existing `.btn` (Cinzel uppercase)
 *   variant="solid"   — filled amber (`.btn-solid`)
 *
 * State props:
 *   loading  — adds a spinner glyph, sets `aria-busy`, disables clicks
 *   success  — flashes a check glyph (caller resets after a tick)
 *   error    — flashes an error tone (caller resets after a tick)
 *
 * Disabled and loading look different: a disabled button is "not ready"
 * (greyed border, idle cursor); a loading button is "in flight"
 * (spinner + wait cursor). This distinction is the Round 20 contract
 * requirement (`§3.3`).
 */
type Variant = "ghost" | "quiet" | "default" | "solid";
type State = "idle" | "loading" | "success" | "error";

type CommonProps = {
  variant?: Variant;
  state?: State;
  loading?: boolean;
  success?: boolean;
  error?: boolean;
  size?: "sm" | "md";
  children: ReactNode;
};

type ButtonProps = CommonProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
    as?: "button";
  };

type AnchorProps = CommonProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "children"> & {
    as: "a";
    href: string;
  };

export type ActionButtonProps = ButtonProps | AnchorProps;

function classesFor(
  variant: Variant,
  size: "sm" | "md",
  state: State,
  extra?: string,
): string {
  const base = ["btn", `btn--${variant}`];
  if (size === "sm") base.push("btn--sm");
  if (state !== "idle") base.push(`btn--${state}`);
  if (extra) base.push(extra);
  return base.join(" ");
}

function resolveState(
  state: State | undefined,
  loading: boolean | undefined,
  success: boolean | undefined,
  error: boolean | undefined,
): State {
  if (state && state !== "idle") return state;
  if (loading) return "loading";
  if (success) return "success";
  if (error) return "error";
  return "idle";
}

const ActionButton = forwardRef<
  HTMLButtonElement | HTMLAnchorElement,
  ActionButtonProps
>(function ActionButton(props, ref) {
  const {
    variant = "default",
    size = "md",
    state,
    loading,
    success,
    error,
    children,
    className,
  } = props;
  const resolved = resolveState(state, loading, success, error);
  const isBusy = resolved === "loading";
  const classes = classesFor(variant, size, resolved, className);
  const content = (
    <>
      {isBusy ? <span className="btn-spinner" aria-hidden="true" /> : null}
      {resolved === "success" ? (
        <span className="btn-glyph" aria-hidden="true">
          ✓
        </span>
      ) : null}
      <span className="btn-label">{children}</span>
    </>
  );

  if (props.as === "a") {
    // Anchor: forward role/aria so screen readers see button-like
    // semantics if the caller really meant a button-styled link.
    const { as: _as, ...rest } = props;
    void _as;
    return (
      <a
        ref={ref as React.Ref<HTMLAnchorElement>}
        {...rest}
        className={classes}
        aria-busy={isBusy ? "true" : undefined}
        data-state={resolved}
      >
        {content}
      </a>
    );
  }

  const { as: _as, disabled, ...rest } = props as ButtonProps;
  void _as;
  return (
    <button
      ref={ref as React.Ref<HTMLButtonElement>}
      {...rest}
      disabled={disabled || isBusy}
      aria-busy={isBusy ? "true" : undefined}
      data-state={resolved}
      className={classes}
    >
      {content}
    </button>
  );
});

export default ActionButton;
