import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { labelLines, type LabelPolicy } from "./label-layout";
const RevealContext = createContext<{
  label: string;
  report: (shortened: boolean) => void;
  hover: (inside: boolean) => void;
} | null>(null);
let context: CanvasRenderingContext2D | null;
export function NodeLabel({
  text,
  policy,
}: {
  text: string;
  policy: LabelPolicy;
}) {
  const ref = useRef<HTMLElement>(null);
  const reveal = useContext(RevealContext);
  const policyKey = JSON.stringify(policy);
  const [result, setResult] = useState({
    lines: [text],
    size: policy.font_size,
  });
  useLayoutEffect(() => {
    const element = ref.current!;
    const parent = element.parentElement!;
    const update = () => {
      context ??= document.createElement("canvas").getContext("2d");
      if (!context) return;
      const css = getComputedStyle(element);
      const width = element.clientWidth;
      const available = Math.max(0, parent.clientHeight - 44);
      let size = policy.font_size,
        formatted = { lines: [] as string[], truncated: true };
      for (; size >= (policy.min_font_size ?? policy.font_size); size--) {
        context.font = `700 ${size}px ${css.fontFamily}`;
        formatted = labelLines(
          text,
          policy,
          width,
          (s) => context!.measureText(s).width,
          Math.min(policy.lines, Math.floor(available / (size * 1.2))),
        );
        if (
          !formatted.truncated ||
          size === (policy.min_font_size ?? policy.font_size)
        )
          break;
      }
      setResult((previous) =>
        previous.size === size &&
        previous.lines.length === formatted.lines.length &&
        previous.lines.every((line, index) => line === formatted.lines[index])
          ? previous
          : { lines: formatted.lines, size },
      );
      reveal?.report(formatted.truncated || text !== reveal.label);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(parent);
    let active = true;
    void document.fonts.ready.then(() => {
      if (active) update();
    });
    return () => {
      active = false;
      observer.disconnect();
    };
  }, [text, policyKey, reveal?.label, reveal?.report]);
  return (
    <strong
      ref={ref}
      className="sgc-node-label"
      onMouseEnter={() => reveal?.hover(true)}
      onMouseLeave={() => reveal?.hover(false)}
      aria-hidden="true"
      style={{ fontSize: result.size, lineHeight: 1.2 }}
    >
      {result.lines.map((line, i) => (
        <span key={i}>{line || "\u00a0"}</span>
      ))}
    </strong>
  );
}
export function LabelContainer({
  label,
  policy,
  opacity,
  children,
}: {
  label: string;
  policy: LabelPolicy;
  opacity?: number;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState(false),
    [focus, setFocus] = useState(false),
    [pinned, setPinned] = useState(false);
  const [copied, setCopied] = useState(false),
    [copyFailed, setCopyFailed] = useState(false);
  const [shortened, setShortened] = useState(false),
    [nameHover, setNameHover] = useState(false),
    [delayed, setDelayed] = useState(false);
  const controls = policy.reveal_mode === "controls";
  useEffect(() => {
    setDelayed(false);
    if (controls || !policy.reveal_hover || !shortened || !nameHover) return;
    const timer = setTimeout(() => setDelayed(true), policy.reveal_delay_ms);
    return () => clearTimeout(timer);
  }, [
    controls,
    policy.reveal_hover,
    policy.reveal_delay_ms,
    shortened,
    nameHover,
    label,
  ]);
  const open = controls
    ? (policy.reveal_hover && hover) ||
      ((policy.reveal_focus ?? true) && focus) ||
      pinned
    : shortened && nameHover && delayed;

  useEffect(() => {
    if (!open && !nameHover) return;
    const close = () => {
      setPinned(false);
      setHover(false);
      setFocus(false);
      setNameHover(false);
      setDelayed(false);
    };
    const scene = ref.current?.closest(".react-flow");
    const onScroll = (event: Event) => {
      if (
        event.target instanceof Element &&
        event.target.closest(".sgc-full-label")
      )
        return;
      close();
    };
    scene?.addEventListener("sgc:scene-change", close);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      scene?.removeEventListener("sgc:scene-change", close);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, nameHover]);

  const rect = open ? ref.current?.getBoundingClientRect() : null;
  return (
    <div
      ref={ref}
      className="sgc-node-container"
      style={{ opacity }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocusCapture={() => setFocus(true)}
      onBlurCapture={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setFocus(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          setPinned(false);
          setHover(false);
          setFocus(false);
          setNameHover(false);
          e.stopPropagation();
        }
      }}
    >
      <RevealContext.Provider
        value={{ label, report: setShortened, hover: setNameHover }}
      >
        {children}
      </RevealContext.Provider>
      {controls && (policy.reveal_button ?? true) && (
        <button
          className="sgc-label-reveal nodrag nopan"
          type="button"
          aria-label={`Show full label: ${label}`}
          aria-expanded={pinned}
          onClick={(e) => {
            e.stopPropagation();
            setPinned((v) => !v);
            setCopied(false);
            setCopyFailed(false);
          }}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Escape") {
              setPinned(false);
              setHover(false);
              setFocus(false);
              setNameHover(false);
            }
          }}
        >
          …
        </button>
      )}
      {open &&
        rect &&
        createPortal(
          <div
            role={pinned ? "dialog" : "tooltip"}
            aria-label={pinned ? "Full node label" : undefined}
            className="sgc-full-label nodrag nopan nowheel"
            onPointerDown={(e) => e.stopPropagation()}
            onWheel={(e) => e.stopPropagation()}
            style={{
              position: "fixed",
              zIndex: 1000000,
              left: Math.max(8, Math.min(rect.left, window.innerWidth - 368)),
              top: Math.max(
                8,
                Math.min(rect.bottom + 6, window.innerHeight - 180),
              ),
              width: "min(350px, calc(100vw - 32px))",
              maxHeight: 160,
              overflow: "auto",
              overflowWrap: "anywhere",
              whiteSpace: "pre-wrap",
              font: "14px/1.4 system-ui",
              color: "#111",
              background: "#fff",
              border: "1px solid #777",
              borderRadius: 6,
              padding: 8,
              boxShadow: "0 2px 8px #0004",
            }}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Escape") {
                setPinned(false);
                setFocus(false);
                setHover(false);
              }
            }}
          >
            <div>{label}</div>
            {pinned && (
              <>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(label);
                      setCopied(true);
                      setCopyFailed(false);
                    } catch {
                      setCopyFailed(true);
                    }
                  }}
                >
                  {copied ? "Copied" : "Copy full label"}
                </button>
                {copyFailed && (
                  <span role="status">
                    {" "}
                    Copy unavailable; select the text above.
                  </span>
                )}{" "}
                <button
                  type="button"
                  onClick={() => {
                    setPinned(false);
                    setFocus(false);
                    setHover(false);
                    ref.current
                      ?.querySelector<HTMLButtonElement>(".sgc-label-reveal")
                      ?.focus();
                    setFocus(false);
                  }}
                >
                  Close
                </button>
              </>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
