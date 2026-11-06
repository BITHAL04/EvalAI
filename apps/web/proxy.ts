import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";

const isProtected = createRouteMatcher(["/teacher(.*)", "/student(.*)", "/admin(.*)", "/dashboard(.*)"]);
const clerk = clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) await auth.protect();
});

/** Without Clerk keys there is nothing to enforce here; the API still rejects every unauthenticated call. */
export default function proxy(req: NextRequest, ev: NextFetchEvent) {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || !process.env.CLERK_SECRET_KEY) return NextResponse.next();
  return clerk(req, ev);
}

export const config = { matcher: ["/((?!_next|.*\\.(?:css|js|png|jpg|svg|ico|woff2?)$).*)", "/(api|trpc)(.*)"] };
