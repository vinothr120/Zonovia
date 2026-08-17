import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./app/AppShell";
import { LoginPage } from "./auth/LoginPage";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { ScanPage } from "./tracking/ScanPage";
import { CategoriesPage } from "./catalog/CategoriesPage";
import { TypesPage } from "./catalog/TypesPage";
import { VendorsPage } from "./catalog/VendorsPage";
import { LocationsPage } from "./locations/LocationsPage";
import { AssetListPage } from "./assets/AssetListPage";
import { AssetFormPage } from "./assets/AssetFormPage";
import { AssetDetailPage } from "./assets/AssetDetailPage";
import { CyclesListPage } from "./inventory/CyclesListPage";
import { CycleFormPage } from "./inventory/CycleFormPage";
import { CycleDetailPage } from "./inventory/CycleDetailPage";
import { TicketsListPage } from "./maintenance/TicketsListPage";
import { TicketFormPage } from "./maintenance/TicketFormPage";
import { TicketDetailPage } from "./maintenance/TicketDetailPage";
import { SchedulesDueReportPage } from "./maintenance/SchedulesDueReportPage";
import { GatewaysListPage } from "./rfid/GatewaysListPage";
import { GatewayFormPage } from "./rfid/GatewayFormPage";
import { RfidTagsListPage } from "./rfid/RfidTagsListPage";
import { ReadEventsPage } from "./rfid/ReadEventsPage";
import { DefinitionsListPage } from "./workflow/DefinitionsListPage";
import { DefinitionFormPage } from "./workflow/DefinitionFormPage";
import { DefinitionDetailPage } from "./workflow/DefinitionDetailPage";
import { MyApprovalsPage } from "./workflow/MyApprovalsPage";
import { InstancesListPage } from "./workflow/InstancesListPage";
import { EvaluateInstancePage } from "./workflow/EvaluateInstancePage";
import { InstanceDetailPage } from "./workflow/InstanceDetailPage";
import { NotificationsPage } from "./workflow/NotificationsPage";

function Protected({ children }: { children: ReactNode }) {
  return (
    <ProtectedRoute>
      <AppShell>{children}</AppShell>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route path="/" element={<Navigate to="/assets" replace />} />

      <Route
        path="/scan"
        element={
          <Protected>
            <div className="max-w-3xl mx-auto">
              <ScanPage />
            </div>
          </Protected>
        }
      />

      <Route
        path="/assets"
        element={
          <Protected>
            <AssetListPage />
          </Protected>
        }
      />
      <Route
        path="/assets/new"
        element={
          <Protected>
            <AssetFormPage />
          </Protected>
        }
      />
      <Route
        path="/assets/:assetId"
        element={
          <Protected>
            <AssetDetailPage />
          </Protected>
        }
      />
      <Route
        path="/assets/:assetId/edit"
        element={
          <Protected>
            <AssetFormPage />
          </Protected>
        }
      />

      <Route
        path="/catalog/categories"
        element={
          <Protected>
            <CategoriesPage />
          </Protected>
        }
      />
      <Route
        path="/catalog/types"
        element={
          <Protected>
            <TypesPage />
          </Protected>
        }
      />
      <Route
        path="/catalog/vendors"
        element={
          <Protected>
            <VendorsPage />
          </Protected>
        }
      />

      <Route
        path="/locations"
        element={
          <Protected>
            <LocationsPage />
          </Protected>
        }
      />

      <Route
        path="/inventory"
        element={
          <Protected>
            <CyclesListPage />
          </Protected>
        }
      />
      <Route
        path="/inventory/new"
        element={
          <Protected>
            <CycleFormPage />
          </Protected>
        }
      />
      <Route
        path="/inventory/:cycleId"
        element={
          <Protected>
            <CycleDetailPage />
          </Protected>
        }
      />

      <Route
        path="/maintenance/tickets"
        element={
          <Protected>
            <TicketsListPage />
          </Protected>
        }
      />
      <Route
        path="/maintenance/tickets/new"
        element={
          <Protected>
            <TicketFormPage />
          </Protected>
        }
      />
      <Route
        path="/maintenance/tickets/:ticketId"
        element={
          <Protected>
            <TicketDetailPage />
          </Protected>
        }
      />
      <Route
        path="/maintenance/schedules/due"
        element={
          <Protected>
            <SchedulesDueReportPage />
          </Protected>
        }
      />

      <Route
        path="/rfid/gateways"
        element={
          <Protected>
            <GatewaysListPage />
          </Protected>
        }
      />
      <Route
        path="/rfid/gateways/new"
        element={
          <Protected>
            <GatewayFormPage />
          </Protected>
        }
      />
      <Route
        path="/rfid/tags"
        element={
          <Protected>
            <RfidTagsListPage />
          </Protected>
        }
      />
      <Route
        path="/rfid/read-events"
        element={
          <Protected>
            <ReadEventsPage />
          </Protected>
        }
      />

      <Route
        path="/workflow/definitions"
        element={
          <Protected>
            <DefinitionsListPage />
          </Protected>
        }
      />
      <Route
        path="/workflow/definitions/new"
        element={
          <Protected>
            <DefinitionFormPage />
          </Protected>
        }
      />
      <Route
        path="/workflow/definitions/:definitionId"
        element={
          <Protected>
            <DefinitionDetailPage />
          </Protected>
        }
      />
      <Route
        path="/workflow/my-approvals"
        element={
          <Protected>
            <MyApprovalsPage />
          </Protected>
        }
      />
      <Route
        path="/workflow/instances"
        element={
          <Protected>
            <InstancesListPage />
          </Protected>
        }
      />
      {/* Must be registered before /workflow/instances/:instanceId — otherwise "evaluate"
          would match the :instanceId param and this route would never be reached. */}
      <Route
        path="/workflow/instances/evaluate"
        element={
          <Protected>
            <EvaluateInstancePage />
          </Protected>
        }
      />
      <Route
        path="/workflow/instances/:instanceId"
        element={
          <Protected>
            <InstanceDetailPage />
          </Protected>
        }
      />

      <Route
        path="/notifications"
        element={
          <Protected>
            <NotificationsPage />
          </Protected>
        }
      />

      <Route path="*" element={<Navigate to="/assets" replace />} />
    </Routes>
  );
}

export default App;
