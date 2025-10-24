/**
 * Jest Configuration
 *
 * Configures Jest for testing frontend code and generating coverage reports
 * that can be merged with backend (Python) coverage for unified reporting.
 */

module.exports = {
  displayName: "frontend",
  testEnvironment: "node",

  // Coverage settings
  collectCoverage: true,
  collectCoverageFrom: [
    "src/**/*.{js,jsx,ts,tsx}",
    "!src/**/*.d.ts",
    "!src/**/index.{js,ts}",
    "!src/**/*.stories.{js,ts}",
  ],

  // Coverage reporters for Codecov compatibility
  coverageReporters: [
    "text",
    "text-summary",
    "json",
    "lcov",
    "xml",  // IMPORTANT: XML format for Codecov
  ],

  // Output coverage to standard location
  coverageDirectory: "./coverage/frontend",

  // Test file patterns
  testMatch: [
    "**/__tests__/**/*.[jt]s?(x)",
    "**/?(*.)+(spec|test).[jt]s?(x)",
  ],

  // Transform settings (if using TypeScript or JSX)
  transform: {
    "^.+\\.tsx?$": "ts-jest",
  },

  // Module paths (update as your frontend structure evolves)
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    "^@components/(.*)$": "<rootDir>/src/components/$1",
    "^@lib/(.*)$": "<rootDir>/src/lib/$1",
  },

  // Don't fail if no tests exist yet (frontend still being built)
  passWithNoTests: process.env.CI === "true",

  // Minimum coverage thresholds (adjustable)
  coverageThreshold: {
    global: {
      branches: 50,
      functions: 50,
      lines: 50,
      statements: 50,
    },
  },
};
