import { describe, test, expect } from "bun:test";
import {
  parseRecallText,
  formatContext,
  matchIdentitySignal,
  doRecall,
} from "./mnemosyne-bridge.ts";

// ===== parseRecallText =====

describe("parseRecallText", () => {
  test("parses single result with all fields", () => {
    const output = `  ID: mem_abc
  Content: User prefers neovim
  Score: 0.85
  Importance: 0.7
  Source: preference
  Timestamp: 2024-01-15T10:30:00
  Veracity: stated`;
    const results = parseRecallText(output);
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({
      id: "mem_abc",
      content: "User prefers neovim",
      source: "preference",
      timestamp: "2024-01-15T10:30:00",
      veracity: "stated",
    });
    expect(results[0].score).toBeCloseTo(0.85);
    expect(results[0].importance).toBeCloseTo(0.7);
  });

  test("parses multiple results separated by blank line", () => {
    const output = `  ID: mem_a
  Content: First memory
  Score: 0.9

  ID: mem_b
  Content: Second memory
  Score: 0.7`;
    const results = parseRecallText(output);
    expect(results).toHaveLength(2);
    expect(results[0].id).toBe("mem_a");
    expect(results[0].content).toBe("First memory");
    expect(results[1].id).toBe("mem_b");
    expect(results[1].content).toBe("Second memory");
  });

  test("skips blocks missing ID or Content", () => {
    const output = `  ID: mem_a
  Content: First
  Score: 0.9

  Some random text without proper fields

  ID: mem_b
  Content: Second
  Score: 0.7`;
    const results = parseRecallText(output);
    expect(results).toHaveLength(2);
  });

  test("defaults missing score to 0", () => {
    const output = `  ID: mem_a
  Content: No score field`;
    const results = parseRecallText(output);
    expect(results).toHaveLength(1);
    expect(results[0].score).toBe(0);
  });

  test("returns empty array for empty input", () => {
    expect(parseRecallText("")).toEqual([]);
  });

  test("handles just score (no optional fields)", () => {
    const output = `  ID: mem_a
  Content: Just the basics
  Score: 0.6`;
    const results = parseRecallText(output);
    expect(results).toHaveLength(1);
    expect(results[0].id).toBe("mem_a");
    expect(results[0].score).toBeCloseTo(0.6);
    expect(results[0].importance).toBeUndefined();
    expect(results[0].source).toBeUndefined();
  });
});

// ===== formatContext =====

describe("formatContext", () => {
  test("formats single row with importance", () => {
    const rows = [
      { id: "m1", content: "User prefers neovim", score: 1, importance: 0.7 },
    ];
    const result = formatContext(rows);
    expect(result).toStartWith("## Mnemosyne Context");
    expect(result).toContain("(importance 0.70)");
    expect(result).toContain("User prefers neovim");
  });

  test("includes source when not conversation", () => {
    const rows = [
      { id: "m1", content: "test", score: 1, importance: 0.5, source: "preference" },
    ];
    expect(formatContext(rows)).toContain("source preference");
  });

  test("omits source tag when conversation", () => {
    const rows = [
      { id: "m1", content: "test", score: 1, importance: 0.5, source: "conversation" },
    ];
    expect(formatContext(rows)).not.toContain("source");
  });

  test("handles missing importance", () => {
    const rows = [{ id: "m1", content: "No imp metadata", score: 1 }];
    const result = formatContext(rows);
    expect(result).toContain("No imp metadata");
    expect(result).not.toContain("(importance");
  });

  test("formats multiple rows", () => {
    const rows = [
      { id: "m1", content: "First", score: 1, importance: 0.7, source: "preference" },
      { id: "m2", content: "Second", score: 1, importance: 0.5 },
    ];
    const result = formatContext(rows);
    const lines = result.split("\n").filter(l => l.startsWith("  "));
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain("First");
    expect(lines[1]).toContain("Second");
  });
});

// ===== matchIdentitySignal =====

describe("matchIdentitySignal", () => {
  test("matches each identity phrase", () => {
    const cases = [
      { phrase: "feeling like", text: "I'm feeling like I own this project" },
      { phrase: "imposter", text: "I have imposter syndrome" },
      { phrase: "impostor", text: "I feel like an impostor" },
      { phrase: "barely know", text: "I barely know nix" },
      { phrase: "don't know my own", text: "I don't know my own setup" },
      { phrase: "don't even know how", text: "I don't even know how to start" },
      { phrase: "want them to feel", text: "I want them to feel included" },
      { phrase: "i'm proud", text: "I'm proud of this solution" },
      { phrase: "i feel like a", text: "I feel like a fraud" },
      { phrase: "i don't know how to", text: "I don't know how to do this" },
    ];
    for (const { phrase, text } of cases) {
      expect(matchIdentitySignal(text)).toBe(true);
    }
  });

  test("is case insensitive", () => {
    expect(matchIdentitySignal("I'M PROUD of this")).toBe(true);
    expect(matchIdentitySignal("I'm Proud of this")).toBe(true);
    expect(matchIdentitySignal("i'm proud of this")).toBe(true);
    expect(matchIdentitySignal("IMPOSTER SYNDROME")).toBe(true);
  });

  test("does not match non-signal text", () => {
    expect(matchIdentitySignal("What is the weather today?")).toBe(false);
    expect(matchIdentitySignal("Run the tests now")).toBe(false);
    expect(matchIdentitySignal("")).toBe(false);
    expect(matchIdentitySignal("Proudly presenting my work")).toBe(false);
    expect(matchIdentitySignal("You should feel proud")).toBe(false);
  });

  test("matches substring within longer text", () => {
    expect(matchIdentitySignal("I'm proud of the work we did today")).toBe(true);
    expect(matchIdentitySignal("Long sentence where I barely know the answer")).toBe(true);
  });

  test("matches only first signal (one per turn)", () => {
    const text = "I'm proud of this and I don't even know how I did it";
    expect(matchIdentitySignal(text)).toBe(true);
  });
});

// ===== doRecall (mock $) =====

describe("doRecall", () => {
  function mock$(returns: string) {
    return (strings: TemplateStringsArray, ...values: any[]) => ({
      quiet: () => ({
        text: async () => returns,
      }),
    });
  }

  test("returns null for empty query", async () => {
    expect(await doRecall(mock$(""), "")).toBeNull();
  });

  test("parses mock output and returns formatted context", async () => {
    const mockOutput = `  ID: mem_a
  Content: User prefers neovim
  Score: 0.85
  Importance: 0.7
  Source: preference

  ID: mem_b
  Content: [ASSISTANT] We refactored the flake
  Score: 0.7
  Importance: 0.15`;

    const result = await doRecall(mock$(mockOutput), "test query");
    expect(result).not.toBeNull();
    expect(result).toContain("## Mnemosyne Context");
    expect(result).toContain("User prefers neovim");
    expect(result).toContain("(importance 0.70, source preference)");
    expect(result).toContain("source preference");
    expect(result).not.toContain("We refactored the flake");
  });

  test("caps results at RECALL_CAP (5)", async () => {
    const rows = Array.from({ length: 7 }, (_, i) => `  ID: mem_${i}
  Content: Memory ${i}
  Score: ${(1 - i / 10).toFixed(1)}`);
    const mockOutput = rows.join("\n\n");

    const result = await doRecall(mock$(mockOutput), "test query");
    expect(result).not.toBeNull();
    const lines = result!.split("\n").filter(l => l.startsWith("  "));
    expect(lines.length).toBeLessThanOrEqual(5);
  });

  test("filters out [ASSISTANT]-prefixed results", async () => {
    const mockOutput = `  ID: mem_a
  Content: [ASSISTANT] Something
  Score: 0.9

  ID: mem_b
  Content: [ASSISTANT] Another
  Score: 0.8`;

    const result = await doRecall(mock$(mockOutput), "test query");
    expect(result).toBeNull();
  });

  test("returns null when nix shell throws", async () => {
    const throwing$ = (_strings: TemplateStringsArray, ..._values: any[]) => ({
      quiet: () => ({
        text: async () => {
          throw new Error("nix shell failed");
        },
      }),
    });
    const result = await doRecall(throwing$, "test query");
    expect(result).toBeNull();
  });

  test("keeps only top RECALL_CAP after filtering", async () => {
    const mockOutput = `  ID: mem_a
  Content: [ASSISTANT] Filtered
  Score: 0.9

  ID: mem_b
  Content: Kept one
  Score: 0.7

  ID: mem_c
  Content: Kept two
  Score: 0.6

  ID: mem_d
  Content: Kept three
  Score: 0.5

  ID: mem_e
  Content: Kept four
  Score: 0.4

  ID: mem_f
  Content: Kept five
  Score: 0.3

  ID: mem_g
  Content: Dropped
  Score: 0.2`;

    const result = await doRecall(mock$(mockOutput), "test query");
    expect(result).not.toBeNull();
    expect(result).toContain("Kept one");
    expect(result).toContain("Kept five");
    expect(result).not.toContain("Dropped");
  });
});
