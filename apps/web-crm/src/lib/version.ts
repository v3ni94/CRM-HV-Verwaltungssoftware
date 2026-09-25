import pkg from "../../package.json";

import { CURRENT_VERSION } from "./changelog";

export const SERVICE_NAME = "web-crm";

/** Semantische Version aus dem Versionsverlauf, überstimmbar per MHVP_APP_VERSION. */
export function appVersion(): string {
  return process.env.MHVP_APP_VERSION || CURRENT_VERSION || pkg.version;
}

/** Build-Kennung (Git-Hash) aus MHVP_BUILD, leer wenn nicht gesetzt. */
export function appBuild(): string {
  return process.env.MHVP_BUILD || "";
}
