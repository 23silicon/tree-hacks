import { useState } from "react";
import GraphCanvas from "./graph/GraphCanvas";
import LandingPage from "./LandingPage";
import { GooeySearchBar } from "@/components/ui/animated-search-bar";

export default function App() {
  const [showGraph, setShowGraph] = useState(false);

  if (!showGraph) {
    return (
      <LandingPage
        onEnter={() => setShowGraph(true)}
        onBrandClick={() => window.location.reload()}
      />
    );
  }

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col">
      <button
        type="button"
        onClick={() => setShowGraph(false)}
        className="absolute left-4 top-4 z-40 cursor-pointer text-base font-semibold tracking-wide text-white transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 md:left-6 md:top-6 md:text-lg"
        aria-label="Return to main page"
      >
        Sentimentree
      </button>
      <GooeySearchBar />
      <div className="relative min-h-0 flex-1">
        <GraphCanvas />
      </div>
    </div>
  );
}
