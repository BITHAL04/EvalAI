export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const CLERK_KEY = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
/**
 * "test" lets automated browser tests supply a signed JWT directly. It grants nothing by itself:
 * the API still verifies every token against its configured JWKS. Never set it on Vercel.
 */
export const AUTH_MODE: "clerk" | "test" | "none" = CLERK_KEY ? "clerk" : process.env.NEXT_PUBLIC_AUTH_MODE === "test" ? "test" : "none";
