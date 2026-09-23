import pkg from "../../package.json";

export const SERVICE_NAME = "web-portal";

export function appVersion(): string {
  return process.env.MHVP_APP_VERSION || pkg.version;
}
