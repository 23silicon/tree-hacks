import { HeroGeometric } from "@/components/ui/shape-landing-hero";
import { GooeySearchBar } from "@/components/ui/animated-search-bar";

export default function LandingPage({ onEnter, onBrandClick }) {
  return (
    <HeroGeometric onBrandClick={onBrandClick}>
      <div className="w-full max-w-2xl">
        <GooeySearchBar onEnterGraph={onEnter} />
      </div>
    </HeroGeometric>
  );
}
