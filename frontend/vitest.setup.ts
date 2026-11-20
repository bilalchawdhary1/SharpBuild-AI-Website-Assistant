import "@testing-library/jest-dom/vitest";
import {cleanup, configure} from "@testing-library/react";
import {afterEach} from "vitest";

// findBy* / waitFor wait up to 5 s instead of 1 s. The chat's typing effect needs real timers, so on a
// busy or slow machine (many jsdom workers at once) a 1 s limit fails tests that are actually fine.
configure({asyncUtilTimeout: 5000});

afterEach(() => cleanup());
