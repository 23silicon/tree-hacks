import { useState, useRef } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";
import { motion } from "framer-motion";

import "./graph-search-bar.css";

export const GraphSearchBar = () => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [searchText, setSearchText] = useState("");
  const [isFocused, setIsFocused] = useState(false);

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const handleInputKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setSearchText("");
      setIsFocused(false);
    }
  };

  return (
    <motion.div
      className="graph-search-bar"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2, duration: 0.4 }}
    >
      <motion.div
        className="graph-search-inner"
        animate={isFocused ? { scale: 1.02 } : { scale: 1 }}
        transition={{ type: "spring", stiffness: 400, damping: 30 }}
      >
        <input
          ref={inputRef}
          type="text"
          className="graph-search-input"
          placeholder="Search predictions..."
          value={searchText}
          onChange={handleInputChange}
          onKeyDown={handleInputKeyDown}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          aria-label="Search predictions"
        />
      </motion.div>
    </motion.div>
  );
};
