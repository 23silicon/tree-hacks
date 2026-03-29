import { useState } from "react";
import GraphCanvas from "./graph/GraphCanvas";
import LandingPage from "./LandingPage";
import { GooeySearchBar } from "@/components/ui/animated-search-bar";

export default function App() {
  const [showGraph, setShowGraph] = useState(false);

  if (!showGraph) {
    return <LandingPage onEnter={() => setShowGraph(true)} />;
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <GooeySearchBar />
      <div className="relative min-h-0 flex-1">
        <GraphCanvas />
      </div>
    </div>
  );
}
