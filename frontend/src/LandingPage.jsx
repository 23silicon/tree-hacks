import { HeroGeometric } from "@/components/ui/shape-landing-hero";
import { GooeySearchBar } from "@/components/ui/animated-search-bar";

export default function LandingPage({ onSearch, error }) {
  return (
    <HeroGeometric>
      <div className="w-full max-w-2xl space-y-4">
        <GooeySearchBar onSearch={onSearch} />
        {error ? (
          <div className="rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {error}
          </div>
        ) : null}
      </div>
    </HeroGeometric>
  );
}
