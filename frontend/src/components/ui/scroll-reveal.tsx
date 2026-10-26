import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface ScrollRevealProps {
  children: ReactNode;
  className?: string;
  delay?: number; // ms
  duration?: number; // ms
  direction?: "up" | "down" | "left" | "right" | "none";
  distance?: number; // px
  threshold?: number;
  rootMargin?: string;
  once?: boolean;
  scale?: number; // Initial scale (e.g. 0.95 for subtle zoom in)
}

/**
 * ScrollReveal smoothly fades and slides elements into view as they enter the viewport.
 * Uses IntersectionObserver for smooth 60/120fps CSS transitions with cubic-bezier easing.
 */
export function ScrollReveal({
  children,
  className,
  delay = 0,
  duration = 800,
  direction = "up",
  distance = 32,
  threshold = 0.12,
  rootMargin = "0px 0px -40px 0px",
  once = true,
  scale = 1,
}: ScrollRevealProps) {
  const [isVisible, setIsVisible] = useState(false);
  const elementRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = elementRef.current;
    if (!el) return;

    // Fallback if IntersectionObserver is not supported
    if (typeof IntersectionObserver === "undefined") {
      setIsVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        if (entry.isIntersecting) {
          setIsVisible(true);
          if (once) {
            observer.unobserve(el);
          }
        } else if (!once) {
          setIsVisible(false);
        }
      },
      { threshold, rootMargin },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold, rootMargin, once]);

  const getTransform = () => {
    if (isVisible) return "translate3d(0, 0, 0) scale(1)";

    const scaleTransform = scale !== 1 ? ` scale(${scale})` : "";

    switch (direction) {
      case "up":
        return `translate3d(0, ${distance}px, 0)${scaleTransform}`;
      case "down":
        return `translate3d(0, -${distance}px, 0)${scaleTransform}`;
      case "left":
        return `translate3d(${distance}px, 0, 0)${scaleTransform}`;
      case "right":
        return `translate3d(-${distance}px, 0, 0)${scaleTransform}`;
      case "none":
        return `translate3d(0, 0, 0)${scaleTransform}`;
    }
  };

  return (
    <div
      ref={elementRef}
      className={cn("will-change-[transform,opacity]", className)}
      style={{
        opacity: isVisible ? 1 : 0,
        transform: getTransform(),
        transitionDuration: `${duration}ms`,
        transitionDelay: `${delay}ms`,
        transitionProperty: "opacity, transform",
        transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      {children}
    </div>
  );
}
