import GraphCanvas from "./graph/GraphCanvas";
import { GooeySearchBar } from "@/components/ui/animated-search-bar";

export default function App() {
  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <GooeySearchBar />
      <div className="relative min-h-0 flex-1">
        <GraphCanvas />
      </div>
    </div>
  );
}
