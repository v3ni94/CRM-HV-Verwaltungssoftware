"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { type MeteringConnection, type MeteringProvider } from "@/lib/metering";
import { ui } from "@/lib/ui";

import { AssignmentsCsv } from "./AssignmentsCsv";
import { AssignmentsTable } from "./AssignmentsTable";
import { AssignmentWizard } from "./AssignmentWizard";
import { ConnectionsAdmin } from "./ConnectionsAdmin";
import { MeteringDisabledNotice } from "./MeteringDisabledNotice";
import { TransmissionsOverview } from "./TransmissionsOverview";

/** Client shell of the settings page: connections, central assignment overview (same wizard
 *  and table as the object tab), CSV import and export, disabled state of the module. */
export function MeteringSettings({
  providers,
  connections: initial,
  loadFailed = false,
  moduleEnabled,
  permissions,
}: {
  providers: MeteringProvider[];
  connections: MeteringConnection[];
  loadFailed?: boolean;
  moduleEnabled: boolean;
  permissions: string[];
}) {
  const t = useTranslations("Metering");
  const canManage = permissions.includes("metering_connections:manage") && moduleEnabled;
  const canUpdate = permissions.includes("metering_assignments:update") && moduleEnabled;
  const [connections, setConnections] = useState(initial);
  const [wizard, setWizard] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  return (
    <div className="flex flex-col gap-6" data-testid="metering-settings">
      {moduleEnabled ? null : <MeteringDisabledNotice />}
      <section className="flex flex-col gap-3">
        <h2 className={ui.h2}>{t("connection.title")}</h2>
        <ConnectionsAdmin
          initial={connections}
          providers={providers}
          canManage={canManage}
          loadFailed={loadFailed}
          onChange={setConnections}
          onGoToAssignments={() => {
            setWizard(true);
            document.getElementById("zuordnungen")?.scrollIntoView({ behavior: "smooth" });
          }}
        />
      </section>
      <section className="flex flex-col gap-3" id="zuordnungen">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className={ui.h2}>{t("assignment.overviewTitle")}</h2>
          {canUpdate && !wizard ? (
            <button type="button" className={ui.primary} onClick={() => setWizard(true)} disabled={connections.length === 0}>
              {t("assignment.new")}
            </button>
          ) : null}
        </div>
        {wizard ? (
          <AssignmentWizard
            connections={connections}
            onCreated={() => {
              setWizard(false);
              setReloadKey((k) => k + 1);
            }}
            onCancel={() => setWizard(false)}
          />
        ) : null}
        <AssignmentsTable connections={connections} canUpdate={canUpdate} reloadKey={reloadKey} />
      </section>
      <AssignmentsCsv canUpdate={canUpdate} onApplied={() => setReloadKey((k) => k + 1)} />
      <TransmissionsOverview canPoll={canUpdate} reloadKey={reloadKey} />
    </div>
  );
}
