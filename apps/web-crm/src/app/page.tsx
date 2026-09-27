import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { COOKIE } from "@/lib/session";

/** Root route: no content page of its own (operator 27.09.2026). Signed-in users go straight
 *  to the start dashboard, everyone else to the login page; `/` never renders anything itself. */
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const store = await cookies();
  const signedIn = !!store.get(COOKIE.refresh);
  redirect(signedIn ? "/start" : "/anmelden");
}
